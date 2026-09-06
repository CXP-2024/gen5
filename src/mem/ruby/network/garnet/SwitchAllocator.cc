/*
 * Copyright (c) 2020 Inria
 * Copyright (c) 2016 Georgia Institute of Technology
 * Copyright (c) 2008 Princeton University
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are
 * met: redistributions of source code must retain the above copyright
 * notice, this list of conditions and the following disclaimer;
 * redistributions in binary form must reproduce the above copyright
 * notice, this list of conditions and the following disclaimer in the
 * documentation and/or other materials provided with the distribution;
 * neither the name of the copyright holders nor the names of its
 * contributors may be used to endorse or promote products derived from
 * this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 * A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
 * OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
 * LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 * THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */


#include "mem/ruby/network/garnet/SwitchAllocator.hh"

#include "debug/RubyNetwork.hh"
#include "mem/ruby/network/garnet/GarnetNetwork.hh"
#include "mem/ruby/network/garnet/InputUnit.hh"
#include "mem/ruby/network/garnet/OutputUnit.hh"
#include "mem/ruby/network/garnet/Router.hh"

namespace gem5
{

namespace ruby
{

namespace garnet
{

SwitchAllocator::SwitchAllocator(Router *router)
    : Consumer(router)
{
    m_router = router;
    m_num_vcs = m_router->get_num_vcs();
    m_vc_per_vnet = m_router->get_vc_per_vnet();

    m_input_arbiter_activity = 0;
    m_output_arbiter_activity = 0;
}

void
SwitchAllocator::init()
{
    m_num_inports = m_router->get_num_inports();
    m_num_outports = m_router->get_num_outports();
    m_round_robin_inport.resize(m_num_outports);
    m_round_robin_invc.resize(m_num_inports);
    m_port_requests.resize(m_num_inports);
    m_vc_winners.resize(m_num_inports);
    m_escape_requests.resize(m_num_inports);
    m_request_source_inport.resize(m_num_inports);
    m_dpphys_flat_winner.resize(m_num_inports);
    m_dpphys_bank_rr.assign(3, std::vector<int>(4, 0));

    for (int i = 0; i < m_num_inports; i++) {
        m_round_robin_invc[i] = 0;
        m_port_requests[i] = -1;
        m_vc_winners[i] = -1;
        m_escape_requests[i] = false;
        m_request_source_inport[i] = i;
        m_dpphys_flat_winner[i] = -1;
    }

    for (int i = 0; i < m_num_outports; i++) {
        m_round_robin_inport[i] = 0;
    }
}

/*
 * The wakeup function of the SwitchAllocator performs a 2-stage
 * seperable switch allocation. At the end of the 2nd stage, a free
 * output VC is assigned to the winning flits of each output port.
 * There is no separate VCAllocator stage like the one in garnet1.0.
 * At the end of this function, the router is rescheduled to wakeup
 * next cycle for peforming SA for any flits ready next cycle.
 */

void
SwitchAllocator::wakeup()
{
    arbitrate_inports(); // First stage of allocation
    arbitrate_outports(); // Second stage of allocation

    clear_request_vector();
    check_for_wakeup();
}

/*
 * SA-I (or SA-i) loops through all input VCs at every input port,
 * and selects one in a round robin manner.
 *    - For HEAD/HEAD_TAIL flits only selects an input VC whose output port
 *     has at least one free output VC.
 *    - For BODY/TAIL flits, only selects an input VC that has credits
 *      in its output VC.
 * Places a request for the output port from this input VC.
 */

void
SwitchAllocator::arbitrate_inports()
{
    std::vector<bool> paired_inports(m_num_inports, false);
    if (m_router->get_net_ptr()->isDPPhysEnabled())
        arbitrate_dp_phys_inports(paired_inports);

    // Select a VC from each input in a round robin manner
    // Independent arbiter at each input port
    for (int inport = 0; inport < m_num_inports; inport++) {
        if (m_port_requests[inport] >= 0)
            continue;
        int invc = m_round_robin_invc[inport];

        for (int invc_iter = 0; invc_iter < m_num_vcs; invc_iter++) {
            const int vnet = get_vnet(invc);
            auto *net = m_router->get_net_ptr();
            auto *input = m_router->getInputUnit(inport);
            if (!(paired_inports[inport] &&
                  net->dpPhysGoverns(vnet, input->get_direction())) &&
                try_request(inport, invc, inport))
                break;

            invc++;
            if (invc >= m_num_vcs)
                invc = 0;
        }
    }
}

// The paired-pool organization has two read banks: the selected direction's
// private RES bank and one shared POOL bank. Opposing directions use opposite
// phases, so exactly one side can query POOL each cycle. A pool candidate is
// selected across both physical InputUnits and travels through the crossbar
// lane belonging to its true ingress direction; this models a central 1R pool
// even when the backing slot is physically hosted by the opposite InputUnit.
void
SwitchAllocator::arbitrate_dp_phys_inports(
    std::vector<bool> &paired_inports)
{
    auto *net = m_router->get_net_ptr();
    static const PortDirection directions[6] = {
        "East", "West", "North", "South", "Up", "Down"
    };
    const int pool_side =
        (static_cast<uint64_t>(m_router->curCycle()) & 1) == 0 ? 1 : 0;
    const int flat_count = 2 * m_num_vcs;

    for (int pair = 0; pair < 3; ++pair) {
        const int pair_inports[2] = {
            m_router->getInportIdByDirection(directions[pair * 2]),
            m_router->getInportIdByDirection(directions[pair * 2 + 1])
        };
        assert(pair_inports[0] >= 0 && pair_inports[1] >= 0);
        paired_inports[pair_inports[0]] = true;
        paired_inports[pair_inports[1]] = true;

        for (int side = 0; side < 2; ++side) {
            const bool pool_turn = side == pool_side;
            const int bank = pool_turn ? 1 : 0;
            const int request_inport = pair_inports[side];
            int flat = m_dpphys_bank_rr[pair][side * 2 + bank];

            for (int iter = 0; iter < flat_count; ++iter) {
                const int source_inport =
                    pair_inports[flat / m_num_vcs];
                const int invc = flat % m_num_vcs;
                auto *input = m_router->getInputUnit(source_inport);
                const int vnet = get_vnet(invc);
                const bool ready = input->need_stage(invc, SA_, curTick());
                if (ready &&
                    net->dpPhysGoverns(vnet, input->get_direction())) {
                    const int true_d = GarnetNetwork::dpPhysDirnIndex(
                        input->get_true_direction(invc));
                    const bool pooled = net->dpPhysPhysicalPooledOffset(
                        invc % m_vc_per_vnet);
                    if (true_d == pair * 2 + side &&
                        pooled == pool_turn &&
                        try_request(source_inport, invc, request_inport)) {
                        m_dpphys_flat_winner[request_inport] = flat;
                        break;
                    }
                }
                flat = (flat + 1) % flat_count;
            }
        }
    }
}

bool
SwitchAllocator::try_request(int source_inport, int invc,
                             int request_inport)
{
    auto input_unit = m_router->getInputUnit(source_inport);
    if (!input_unit->need_stage(invc, SA_, curTick()))
        return false;

    int outport = input_unit->get_outport(invc);
    const int vnet = get_vnet(invc);
    bool wormhole_control = m_router->get_net_ptr()->isWormhole() &&
        m_router->get_net_ptr()->get_vnet_type(vnet) == CTRL_VNET_;
    if (wormhole_control)
        outport = input_unit->peekTopFlit(invc)->get_outport();
    const int outvc = input_unit->get_outvc(invc);
    bool route_available = true;
    bool escape_request = false;

    if (m_router->get_net_ptr()->isTorus3DAdaptive()) {
        if (outvc == -1) {
            AdaptiveRouteDecision decision =
                m_router->route_compute_3d_adaptive(
                    input_unit->peekTopFlit(invc)->get_route(), invc, true);
            route_available = decision.outport != -1;
            if (route_available) {
                outport = decision.outport;
                escape_request = decision.escape;
                input_unit->grant_outport(invc, outport);
            }
        } else {
            const int escape_vcs =
                m_router->get_net_ptr()->getEscapeVCs();
            const int output_vcs =
                m_router->getOutputUnit(outport)->getVcsPerVnet();
            const bool dpphys = m_router->get_net_ptr()->dpPhysGoverns(
                vnet, m_router->getOutputUnit(outport)->get_direction());
            const int escape_begin = dpphys ?
                m_router->get_net_ptr()->getDPPhysPrivateVCs() +
                    m_router->get_net_ptr()->getDPPhysPoolVCs() :
                m_vc_per_vnet - escape_vcs;
            escape_request = escape_vcs > 0 &&
                outvc % output_vcs >= escape_begin;
        }
    }

    if (!route_available ||
        !send_allowed(source_inport, invc, outport, outvc, escape_request))
        return false;

    m_input_arbiter_activity++;
    m_port_requests[request_inport] = outport;
    m_vc_winners[request_inport] = invc;
    m_escape_requests[request_inport] = escape_request;
    m_request_source_inport[request_inport] = source_inport;
    return true;
}

/*
 * SA-II (or SA-o) loops through all output ports,
 * and selects one input VC (that placed a request during SA-I)
 * as the winner for this output port in a round robin manner.
 *      - For HEAD/HEAD_TAIL flits, performs simplified outvc allocation.
 *        (i.e., select a free VC from the output port).
 *      - For BODY/TAIL flits, decrement a credit in the output vc.
 * The winning flit is read out from the input VC and sent to the
 * CrossbarSwitch.
 * An increment_credit signal is sent from the InputUnit
 * to the upstream router. For HEAD_TAIL/TAIL flits, is_free_signal in the
 * credit is set to true.
 */

void
SwitchAllocator::arbitrate_outports()
{
    // Now there are a set of input vc requests for output vcs.
    // Again do round robin arbitration on these requests
    // Independent arbiter at each output port
    for (int outport = 0; outport < m_num_outports; outport++) {
        int inport = m_round_robin_inport[outport];

        for (int inport_iter = 0; inport_iter < m_num_inports;
                 inport_iter++) {

            // inport has a request this cycle for outport
            if (m_port_requests[inport] == outport) {
                auto output_unit = m_router->getOutputUnit(outport);
                const int source_inport = m_request_source_inport[inport];
                auto input_unit = m_router->getInputUnit(source_inport);

                // grant this outport to this inport
                int invc = m_vc_winners[inport];

                int outvc = input_unit->get_outvc(invc);
                if (outvc == -1) {
                    // VC Allocation - select any free VC from outport
                    outvc = vc_allocate(
                        outport, source_inport, invc,
                        m_escape_requests[inport]);
                }

                // remove flit from Input VC
                flit *t_flit = input_unit->getTopFlit(invc);

                DPRINTF(RubyNetwork, "SwitchAllocator at Router %d "
                                     "granted outvc %d at outport %d "
                                     "to invc %d at inport %d to flit %s at "
                                     "cycle: %lld\n",
                        m_router->get_id(), outvc,
                        m_router->getPortDirectionName(
                            output_unit->get_direction()),
                        invc,
                        m_router->getPortDirectionName(
                            input_unit->get_direction()),
                            *t_flit,
                        m_router->curCycle());


                // Update outport field in the flit since this is
                // used by CrossbarSwitch code to send it out of
                // correct outport.
                // Note: post route compute in InputUnit,
                // outport is updated in VC, but not in flit
                t_flit->set_outport(outport);

                // set outvc (i.e., invc for next hop) in flit
                // (This was updated in VC by vc_allocate, but not in flit)
                t_flit->set_vc(outvc);

                if (m_router->get_net_ptr()->isTorus3DAdaptive() &&
                    output_unit->get_direction() != "Local") {
                    auto *net = m_router->get_net_ptr();
                    const int escape_vcs =
                        net->getEscapeVCs();
                    const int adaptive_vcs = m_vc_per_vnet - escape_vcs;
                    const bool dpphys = net->dpPhysGoverns(
                        get_vnet(invc), output_unit->get_direction());
                    const int output_offset = outvc %
                        output_unit->getVcsPerVnet();
                    const bool output_escape = dpphys ?
                        output_offset >=
                            static_cast<int>(net->getDPPhysPrivateVCs() +
                                             net->getDPPhysPoolVCs()) :
                        escape_vcs > 0 &&
                            output_offset >= adaptive_vcs;
                    const bool input_escape =
                        escape_vcs > 0 &&
                        invc % m_vc_per_vnet >= adaptive_vcs;
                    if (output_escape)
                        m_router->get_net_ptr()->increment_escape_hop();
                    else
                        m_router->get_net_ptr()->increment_adaptive_hop();
                    const bool packet_head =
                        t_flit->get_type() == HEAD_ ||
                        t_flit->get_type() == HEAD_TAIL_;
                    if (output_escape && !input_escape && packet_head) {
                        m_router->get_net_ptr()->
                            increment_escape_transition();
                    }
                }

                // decrement credit in outvc
                output_unit->decrement_credit(outvc);

                // CBS: an in-ring transit packet may displace the critical
                // bubble. When it fills the last free slot at the marked
                // downstream inport, the mark moves upstream to the slot
                // this packet vacates (freed below for single-flit ctrl
                // packets).
                {
                    const int cbs_vnet = get_vnet(invc);
                    if (cbs_governs(cbs_vnet, outport)) {
                        auto *net = m_router->get_net_ptr();
                        PortDirection outport_dirn =
                            output_unit->get_direction();
                        PortDirection down_inport =
                            GarnetNetwork::cbsOppositeDirn(outport_dirn);
                        int down_router = net->cbsDownstreamRouter(
                            m_router->get_id(), outport_dirn);
                        // Under DP the bubble lives in the dedicated
                        // window: displacement fires when the consumed
                        // slot and the vacated slot are both dedicated
                        // and no dedicated slot stays free downstream.
                        const bool dp = net->isDPEnabled();
                        const int dp_r =
                            dp ? (int)net->getDPReserve() : 0;
                        const bool bubble_consumed = dp ?
                            (outvc % m_vc_per_vnet < dp_r &&
                             invc % m_vc_per_vnet < dp_r &&
                             output_unit->free_vc_credit_count(
                                 cbs_vnet, 0, dp_r) == 0) :
                            output_unit->count_free_vcs(cbs_vnet) == 0;
                        if (input_unit->get_direction() == down_inport &&
                            net->cbsHasMark(down_router, down_inport,
                                            cbs_vnet) &&
                            bubble_consumed) {
                            net->cbsMoveMark(down_router, down_inport,
                                m_router->get_id(),
                                input_unit->get_direction(), cbs_vnet);
                        }
                    }
                }

                // flit ready for Switch Traversal
                t_flit->advance_stage(ST_, curTick());
                // `inport` is the true-direction crossbar lane. For a pool
                // flit, `input_unit` may be the opposite physical host.
                m_router->grant_switch(inport, t_flit);
                m_output_arbiter_activity++;

                if ((t_flit->get_type() == TAIL_) ||
                    t_flit->get_type() == HEAD_TAIL_) {
                    bool wormhole_control =
                        m_router->get_net_ptr()->isWormhole() &&
                        m_router->get_net_ptr()->get_vnet_type(
                            get_vnet(invc)) == CTRL_VNET_;
                    bool input_has_next = input_unit->isReady(invc, curTick());

                    if (!wormhole_control || !input_has_next)
                        assert(!(input_unit->isReady(invc, curTick())));

                    if (wormhole_control && input_has_next) {
                        // Keep the input VC active while queued
                        // HEAD_TAIL packets drain, but route the next flit
                        // independently.
                        input_unit->set_outvc(invc, -1);
                        input_unit->increment_credit(invc, false, curTick());
                    } else {
                        input_unit->set_vc_idle(invc, curTick());
                        input_unit->increment_credit(invc, true, curTick());
                    }
                } else {
                    // Send a credit back
                    // but do not indicate that the VC is idle
                    input_unit->increment_credit(invc, false, curTick());
                }

                // remove this request
                m_port_requests[inport] = -1;

                // Update Round Robin pointer
                m_round_robin_inport[outport] = inport + 1;
                if (m_round_robin_inport[outport] >= m_num_inports)
                    m_round_robin_inport[outport] = 0;

                // Update Round Robin pointer to the next VC
                // We do it here to keep it fair.
                // Only the VC which got switch traversal
                // is updated.
                m_round_robin_invc[source_inport] = invc + 1;
                if (m_round_robin_invc[source_inport] >= m_num_vcs)
                    m_round_robin_invc[source_inport] = 0;

                const int flat_winner = m_dpphys_flat_winner[inport];
                if (flat_winner >= 0) {
                    auto *net = m_router->get_net_ptr();
                    const int true_d = GarnetNetwork::dpPhysDirnIndex(
                        input_unit->get_true_direction(invc));
                    assert(true_d >= 0);
                    const int pair = true_d / 2;
                    const int side = true_d % 2;
                    const bool pooled = net->dpPhysPhysicalPooledOffset(
                        invc % m_vc_per_vnet);
                    const int bank = pooled ? 1 : 0;
                    m_dpphys_bank_rr[pair][side * 2 + bank] =
                        (flat_winner + 1) % (2 * m_num_vcs);
                    if (pooled)
                        net->increment_dp_phys_pool_read(true_d);
                    else
                        net->increment_dp_phys_reserved_read(true_d);
                }


                break; // got a input winner for this outport
            }

            inport++;
            if (inport >= m_num_inports)
                inport = 0;
        }
    }
}

// CBS applies to hops that stay inside the torus (non-Local outports) on
// ctrl vnets, where every packet is a single flit and a buffer slot is
// exactly one VC.
bool
SwitchAllocator::cbs_governs(int vnet, int outport)
{
    auto *net = m_router->get_net_ptr();
    return net->isCBSEnabled() &&
           net->get_vnet_type(vnet) == CTRL_VNET_ &&
           m_router->getOutputUnit(outport)->get_direction() != "Local";
}

// DP applies to the same hops as CBS: non-Local outports on ctrl vnets.
bool
SwitchAllocator::dp_governs(int vnet, int outport)
{
    auto *net = m_router->get_net_ptr();
    return net->isDPEnabled() &&
           net->get_vnet_type(vnet) == CTRL_VNET_ &&
           m_router->getOutputUnit(outport)->get_direction() != "Local";
}

// DP on Torus3D DOR: decide which windows at `outport` may admit the flit
// waiting in (inport, invc). The pooled window [dp_reserve, V) is open when
// it has a free VC and the downstream dimension pair is under its cap. The
// dedicated window [0, dp_reserve) runs CBS: ring entry next to the
// critical bubble needs two free dedicated slots, and in-ring transit may
// fill the last dedicated slot at a marked inport only when the mover
// itself sits in a dedicated VC, so the mark lands on the dedicated slot
// it vacates.
void
SwitchAllocator::dp_cbs_admission(int vnet, int inport, int invc, int outport,
                                  bool &shared_ok, bool &dedicated_ok,
                                  bool record_stats)
{
    auto *net = m_router->get_net_ptr();
    auto output_unit = m_router->getOutputUnit(outport);
    const int r = net->getDPReserve();
    const int pooled = m_vc_per_vnet - r;

    const PortDirection outport_dirn = output_unit->get_direction();
    const PortDirection down_inport =
        GarnetNetwork::cbsOppositeDirn(outport_dirn);
    const int down_router =
        net->cbsDownstreamRouter(m_router->get_id(), outport_dirn);
    const bool marked = net->cbsHasMark(down_router, down_inport, vnet);
    const bool ring_entry =
        m_router->getInputUnit(inport)->get_direction() != down_inport;

    const bool pool_full = net->dpPoolFull(down_router, down_inport, vnet);
    const bool shared_free = output_unit->has_free_vc(vnet, r, pooled);
    shared_ok = shared_free && !pool_full;

    const int ded_free = output_unit->free_vc_credit_count(vnet, 0, r);
    if (ring_entry) {
        dedicated_ok = ded_free >= (marked ? 2 : 1);
    } else {
        dedicated_ok = ded_free >= 2 ||
            (ded_free == 1 && (!marked || invc % m_vc_per_vnet < r));
    }

    if (record_stats && !shared_ok && !dedicated_ok) {
        if (shared_free && pool_full)
            net->increment_dp_pool_block();
        if (ring_entry && marked && ded_free == 1)
            net->increment_cbs_entry_block();
    }
}

/*
 * A flit can be sent only if
 * (1) there is at least one free output VC at the
 *     output port (for HEAD/HEAD_TAIL),
 *  or
 * (2) if there is at least one credit (i.e., buffer slot)
 *     within the VC for BODY/TAIL flits of multi-flit packets.
 * and
 * (3) pt-to-pt ordering is not violated in ordered vnets, i.e.,
 *     there should be no other flit in this input port
 *     within an ordered vnet
 *     that arrived before this flit and is requesting the same output port.
 */

bool
SwitchAllocator::send_allowed(int inport, int invc, int outport, int outvc,
                              bool escape_request)
{
    // Check if outvc needed
    // Check if credit needed (for multi-flit packet)
    // Check if ordering violated (in ordered vnet)

    int vnet = get_vnet(invc);
    bool has_outvc = (outvc != -1);
    bool has_credit = false;

    auto output_unit = m_router->getOutputUnit(outport);
    if (!has_outvc) {

        // needs outvc
        // this is only true for HEAD and HEAD_TAIL flits.

        bool output_available = false;
        if (m_router->get_net_ptr()->isTorus3DAdaptive()) {
            auto *net = m_router->get_net_ptr();
            const int escape_vcs = net->getEscapeVCs();
            const int adaptive_vcs = m_vc_per_vnet - escape_vcs;
            const bool dpphys = net->dpPhysGoverns(
                vnet, output_unit->get_direction());
            if (dpphys) {
                output_available = escape_request ?
                    m_router->dpPhysHasEscapeVC(outport, vnet) :
                    m_router->dpPhysAdaptiveFreeCount(outport, vnet) > 0;
            } else {
                const int first_offset = escape_request ? adaptive_vcs : 0;
                const int count = escape_request ? escape_vcs : adaptive_vcs;
                output_available = output_unit->has_free_vc(
                    vnet, first_offset, count);
            }

            // DP: adaptive-class admission also respects the downstream
            // dimension-pair pool; escape VCs stay exempt. Routing already
            // skips pool-full outports, so this is a belt check.
            if (output_available && !escape_request &&
                dp_governs(vnet, outport)) {
                auto *net = m_router->get_net_ptr();
                const PortDirection outport_dirn =
                    output_unit->get_direction();
                if (net->dpPoolFull(
                        net->cbsDownstreamRouter(m_router->get_id(),
                                                 outport_dirn),
                        GarnetNetwork::cbsOppositeDirn(outport_dirn),
                        vnet)) {
                    output_available = false;
                    net->increment_dp_pool_block();
                }
            }
        } else if (dp_governs(vnet, outport)) {
            // DP on DOR: the flit may take a pooled VC (pair under its
            // cap) or a dedicated VC (per CBS rules on the dedicated
            // window); see dp_cbs_admission.
            bool shared_ok, dedicated_ok;
            dp_cbs_admission(vnet, inport, invc, outport,
                             shared_ok, dedicated_ok, true);
            output_available = shared_ok || dedicated_ok;
        } else {
            bool wormhole_control =
                m_router->get_net_ptr()->isWormhole() &&
                m_router->get_net_ptr()->get_vnet_type(vnet) == CTRL_VNET_;
            output_available =
                (wormhole_control && output_unit->has_credit_vc(vnet)) ||
                output_unit->has_free_vc(vnet);

            // CBS: a packet entering a torus ring (injection or dimension
            // change) may not consume the critical bubble. When the
            // downstream inport hosts the mark, ring entry needs one extra
            // free slot so the marked slot stays free.
            if (output_available && cbs_governs(vnet, outport)) {
                auto *net = m_router->get_net_ptr();
                PortDirection outport_dirn = output_unit->get_direction();
                PortDirection down_inport =
                    GarnetNetwork::cbsOppositeDirn(outport_dirn);
                PortDirection inport_dirn =
                    m_router->getInputUnit(inport)->get_direction();
                if (inport_dirn != down_inport) {
                    // ring entry, not in-ring transit
                    int down_router = net->cbsDownstreamRouter(
                        m_router->get_id(), outport_dirn);
                    if (net->cbsHasMark(down_router, down_inport, vnet) &&
                        output_unit->count_free_vcs(vnet) < 2) {
                        output_available = false;
                        net->increment_cbs_entry_block();
                    }
                }
            }
        }
        if (output_available) {

            has_outvc = true;

            // each VC has at least one buffer,
            // so no need for additional credit check
            has_credit = true;
        }
    } else {
        has_credit = output_unit->has_credit(outvc);
    }

    // cannot send if no outvc or no credit.
    if (!has_outvc || !has_credit)
        return false;


    // protocol ordering check
    if ((m_router->get_net_ptr())->isVNetOrdered(vnet)) {
        auto input_unit = m_router->getInputUnit(inport);

        // enqueue time of this flit
        Tick t_enqueue_time = input_unit->get_enqueue_time(invc);

        // check if any other flit is ready for SA and for same output port
        // and was enqueued before this flit
        int vc_base = vnet*m_vc_per_vnet;
        for (int vc_offset = 0; vc_offset < m_vc_per_vnet; vc_offset++) {
            int temp_vc = vc_base + vc_offset;
            int temp_outport = input_unit->get_outport(temp_vc);
            if (m_router->get_net_ptr()->isWormhole() &&
                m_router->get_net_ptr()->get_vnet_type(vnet) == CTRL_VNET_ &&
                input_unit->isReady(temp_vc, curTick())) {
                temp_outport = input_unit->peekTopFlit(temp_vc)->get_outport();
            }
            if (input_unit->need_stage(temp_vc, SA_, curTick()) &&
               (temp_outport == outport) &&
               (input_unit->get_enqueue_time(temp_vc) < t_enqueue_time)) {
                return false;
            }
        }
    }

    return true;
}

// Assign a free VC to the winner of the output port.
int
SwitchAllocator::vc_allocate(int outport, int inport, int invc,
                             bool escape_request)
{
    // Select a free VC from the output port
    int vnet = get_vnet(invc);
    int outvc = -1;
    if (m_router->get_net_ptr()->isTorus3DAdaptive()) {
        auto *net = m_router->get_net_ptr();
        const int escape_vcs = net->getEscapeVCs();
        const int adaptive_vcs = m_vc_per_vnet - escape_vcs;
        const PortDirection outdir =
            m_router->getOutputUnit(outport)->get_direction();
        if (net->dpPhysGoverns(vnet, outdir)) {
            outvc = escape_request ?
                m_router->dpPhysSelectEscapeVC(outport, vnet) :
                m_router->dpPhysSelectAdaptiveVC(outport, vnet);
        } else {
            const int first_offset = escape_request ? adaptive_vcs : 0;
            const int count = escape_request ? escape_vcs : adaptive_vcs;
            outvc = m_router->getOutputUnit(outport)->select_free_vc(
                vnet, first_offset, count);
        }
    } else if (dp_governs(vnet, outport)) {
        // Shared-first: spend pool headroom before the dedicated reserve
        // so the CBS bubbles keep their mobility.
        auto output_unit = m_router->getOutputUnit(outport);
        const int r = m_router->get_net_ptr()->getDPReserve();
        bool shared_ok, dedicated_ok;
        dp_cbs_admission(vnet, inport, invc, outport,
                         shared_ok, dedicated_ok, false);
        if (shared_ok)
            outvc = output_unit->select_free_vc(vnet, r, m_vc_per_vnet - r);
        if (outvc == -1 && dedicated_ok)
            outvc = output_unit->select_free_vc(vnet, 0, r);
    } else {
        bool wormhole_control = m_router->get_net_ptr()->isWormhole() &&
            m_router->get_net_ptr()->get_vnet_type(vnet) == CTRL_VNET_;
        outvc = m_router->getOutputUnit(outport)->select_vc(
            vnet, wormhole_control);
    }

    // has to get a valid VC since it checked before performing SA
    assert(outvc != -1);

    // DP: count the granted VC against its downstream dimension pool
    // (dpNoteAlloc ignores non-pooled offsets, vnets, and directions).
    auto *net = m_router->get_net_ptr();
    if (net->isDPEnabled()) {
        const PortDirection outport_dirn =
            m_router->getOutputUnit(outport)->get_direction();
        if (outport_dirn != "Local") {
            net->dpNoteAlloc(
                net->cbsDownstreamRouter(m_router->get_id(), outport_dirn),
                GarnetNetwork::cbsOppositeDirn(outport_dirn),
                vnet, outvc % m_vc_per_vnet);
        }
    }

    m_router->getInputUnit(inport)->grant_outvc(invc, outvc);
    return outvc;
}

// Wakeup the router next cycle to perform SA again
// if there are flits ready.
void
SwitchAllocator::check_for_wakeup()
{
    Tick nextCycle = m_router->clockEdge(Cycles(1));

    if (m_router->alreadyScheduled(nextCycle)) {
        return;
    }

    for (int i = 0; i < m_num_inports; i++) {
        for (int j = 0; j < m_num_vcs; j++) {
            if (m_router->getInputUnit(i)->need_stage(j, SA_, nextCycle)) {
                m_router->schedule_wakeup(Cycles(1));
                return;
            }
        }
    }
}

int
SwitchAllocator::get_vnet(int invc)
{
    int vnet = invc/m_vc_per_vnet;
    assert(vnet < m_router->get_num_vnets());
    return vnet;
}


// Clear the request vector within the allocator at end of SA-II.
// Was populated by SA-I.
void
SwitchAllocator::clear_request_vector()
{
    std::fill(m_port_requests.begin(), m_port_requests.end(), -1);
    std::fill(m_vc_winners.begin(), m_vc_winners.end(), -1);
    std::fill(m_escape_requests.begin(), m_escape_requests.end(), false);
    std::fill(m_request_source_inport.begin(),
              m_request_source_inport.end(), -1);
    std::fill(m_dpphys_flat_winner.begin(),
              m_dpphys_flat_winner.end(), -1);
}

void
SwitchAllocator::resetStats()
{
    m_input_arbiter_activity = 0;
    m_output_arbiter_activity = 0;
}

} // namespace garnet
} // namespace ruby
} // namespace gem5
