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

#include <algorithm>

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

    for (int i = 0; i < m_num_inports; i++) {
        m_round_robin_invc[i] = 0;
        m_port_requests[i] = -1;
        m_vc_winners[i] = -1;
        m_escape_requests[i] = false;
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
    // Select a VC from each input in a round robin manner
    // Independent arbiter at each input port
    for (int inport = 0; inport < m_num_inports; inport++) {
        int invc = m_round_robin_invc[inport];

        for (int invc_iter = 0; invc_iter < m_num_vcs; invc_iter++) {
            auto input_unit = m_router->getInputUnit(inport);

            if (input_unit->need_stage(invc, SA_, curTick())) {
                // This flit is in SA stage

                int outport = input_unit->get_outport(invc);
                bool wormhole_control =
                    m_router->get_net_ptr()->isWormhole() &&
                    m_router->get_net_ptr()->get_vnet_type(
                        get_vnet(invc)) == CTRL_VNET_;
                if (wormhole_control)
                    outport = input_unit->peekTopFlit(invc)->get_outport();
                int outvc = input_unit->get_outvc(invc);
                bool route_available = true;
                bool escape_request = false;

                if (m_router->get_net_ptr()->isTorus3DAdaptive()) {
                    if (outvc == -1) {
                        AdaptiveRouteDecision decision =
                            m_router->route_compute_3d_adaptive(
                                input_unit->peekTopFlit(invc)->get_route(),
                                invc, true, input_unit->get_direction());
                        route_available = decision.outport != -1;
                        if (route_available) {
                            outport = decision.outport;
                            escape_request = decision.escape;
                            input_unit->grant_outport(invc, outport);
                        }
                    } else {
                        const bool outport_local =
                            m_router->getOutputUnit(outport)->
                                get_direction() == "Local";
                        escape_request = m_router->get_net_ptr()->
                            isEscapeVCAt(outvc, outport_local);
                    }
                }

                // check if the flit in this InputVC is allowed to be sent
                // send_allowed conditions described in that function.
                bool make_request = route_available &&
                    send_allowed(inport, invc, outport, outvc,
                                 escape_request);

                if (make_request) {
                    m_input_arbiter_activity++;
                    m_port_requests[inport] = outport;
                    m_vc_winners[inport] = invc;
                    m_escape_requests[inport] = escape_request;

                    break; // got one vc winner for this port
                }
            }

            invc++;
            if (invc >= m_num_vcs)
                invc = 0;
        }
    }
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
                auto input_unit = m_router->getInputUnit(inport);

                // grant this outport to this inport
                int invc = m_vc_winners[inport];

                int outvc = input_unit->get_outvc(invc);
                if (outvc == -1) {
                    // VC Allocation - select any free VC from outport
                    outvc = vc_allocate(
                        outport, inport, invc, m_escape_requests[inport]);
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
                    const bool output_escape =
                        m_router->get_net_ptr()->isEscapeVCAt(
                            outvc, false);
                    const bool input_escape =
                        m_router->get_net_ptr()->isEscapeVCAt(invc,
                            input_unit->get_direction() == "Local");
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

                if (m_router->get_net_ptr()->isDPPhys() &&
                    output_unit->get_direction() == "Local" &&
                    (t_flit->get_type() == TAIL_ ||
                     t_flit->get_type() == HEAD_TAIL_)) {
                    InputUnit *arrival = input_unit;
                    if (input_unit->get_direction() != "Local") {
                        arrival = m_router->getInputUnit(
                            input_unit->arrivalInport(invc));
                    }
                    m_router->get_net_ptr()->incrementDpphysReceived(
                        arrival->get_direction());
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
                        if (input_unit->get_direction() == down_inport &&
                            net->cbsHasMark(down_router, down_inport,
                                            cbs_vnet) &&
                            output_unit->count_free_vcs(cbs_vnet) == 0) {
                            net->cbsMoveMark(down_router, down_inport,
                                m_router->get_id(),
                                input_unit->get_direction(), cbs_vnet);
                        }
                    }
                }

                // flit ready for Switch Traversal
                t_flit->advance_stage(ST_, curTick());
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
                        grantOnRelease(input_unit, inport, invc, false);
                    } else {
                        input_unit->set_vc_idle(invc, curTick());
                        grantOnRelease(input_unit, inport, invc, true);
                    }
                } else {
                    // Send a credit back
                    // but do not indicate that the VC is idle
                    grantOnRelease(input_unit, inport, invc, false);
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
                m_round_robin_invc[inport] = invc + 1;
                if (m_round_robin_invc[inport] >= m_num_vcs)
                    m_round_robin_invc[inport] = 0;


                break; // got a input winner for this outport
            }

            inport++;
            if (inport >= m_num_inports)
                inport = 0;
        }
    }
}

void
SwitchAllocator::grantOnRelease(InputUnit *input_unit, int inport, int invc,
                                bool free_signal)
{
    auto *net = m_router->get_net_ptr();
    if (!net->isDPPhys() || input_unit->get_direction() == "Local") {
        input_unit->increment_credit(invc, free_signal, curTick());
        return;
    }

    const int arrival = input_unit->arrivalInport(invc);
    assert(arrival >= 0 && arrival < m_num_inports);
    InputUnit *target = m_router->getInputUnit(arrival);
    const int offset = invc % m_vc_per_vnet;

    if (free_signal && net->dpphysIsPoolOffset(offset)) {
        grantPoolCredit(arrival, invc);
        return;
    }

    target->increment_credit(invc, free_signal, curTick());
}

void
SwitchAllocator::handleDpphysReturn(
    const PortDirection &owner_direction, int vc)
{
    auto *net = m_router->get_net_ptr();
    assert(net->dpphysPolicy() == "starve" ||
           net->dpphysPolicy() == "pressure");
    assert(net->dpphysIsPoolOffset(vc % m_vc_per_vnet));
    InputUnit *owner =
        m_router->getInputUnitByDirection(owner_direction);

    const int offset = vc % m_vc_per_vnet;
    const int home_side = net->dpphysHomeSideOfOffset(offset);
    InputUnit *physical = owner;
    if (GarnetNetwork::dpphysSideOfInportDirn(
            owner->get_direction()) != home_side) {
        physical = m_router->getPairedInputUnit(owner->get_id());
    }
    assert(physical->is_vc_idle(vc));
    grantPoolCredit(owner->get_id(), vc);
}

void
SwitchAllocator::grantPoolCredit(int owner_inport, int vc)
{
    auto *net = m_router->get_net_ptr();
    InputUnit *target = m_router->getInputUnit(owner_inport);
    const int offset = vc % m_vc_per_vnet;
    const int vnet = get_vnet(vc);
    const PortDirection owner_dirn = target->get_direction();
    const int pair = GarnetNetwork::dpphysPairOfDirn(owner_dirn);
    const int owner_side =
        GarnetNetwork::dpphysSideOfInportDirn(owner_dirn);
    const int pool_slot = offset - 2 * net->dpphysR();
    assert(pair >= 0 && owner_side >= 0);
    assert(net->dpphysIsPoolOffset(offset));
    assert(m_router->dpphysPoolOwner(pair, vnet, pool_slot) ==
           owner_side);

    int owner_count[2] = {0, 0};
    for (int slot = 0; slot < net->dpphysP(); ++slot) {
        const int owner = m_router->dpphysPoolOwner(pair, vnet, slot);
        assert(owner == 0 || owner == 1);
        owner_count[owner]++;
    }
    assert(owner_count[0] + owner_count[1] == net->dpphysP());

    int target_side = owner_side;
    if (net->dpphysPolicy() == "forced") {
        target_side = 1 - owner_side;
    } else if (net->dpphysPolicy() == "rr") {
        target_side = m_router->dpphysTakeRrSide(pair, vnet);
    } else if (net->dpphysPolicy() == "starve" ||
               net->dpphysPolicy() == "pressure") {
        InputUnit *side_units[2];
        side_units[owner_side] = target;
        side_units[1 - owner_side] =
            m_router->getPairedInputUnit(owner_inport);

        const int vc_base = vnet * m_vc_per_vnet;
        const int reserve = net->dpphysR();
        const int pool = net->dpphysP();
        int free_slots[2] = {0, 0};
        for (int side = 0; side < 2; ++side) {
            for (int reserve_slot = 0;
                 reserve_slot < reserve; ++reserve_slot) {
                const int candidate =
                    vc_base + side * reserve + reserve_slot;
                if (candidate != vc &&
                    side_units[side]->is_vc_idle(candidate)) {
                    free_slots[side]++;
                }
            }
        }
        for (int slot = 0; slot < pool; ++slot) {
            const int owner =
                m_router->dpphysPoolOwner(pair, vnet, slot);
            assert(owner == 0 || owner == 1);
            const int candidate = vc_base + 2 * reserve + slot;
            const int home = net->dpphysHomeSideOfOffset(
                2 * reserve + slot);
            if (candidate != vc &&
                side_units[home]->is_vc_idle(candidate)) {
                free_slots[owner]++;
            }
        }

        if (net->dpphysPolicy() == "pressure") {
            int reserve_busy[2] = {0, 0};
            for (int side = 0; side < 2; ++side) {
                for (int reserve_slot = 0;
                     reserve_slot < reserve; ++reserve_slot) {
                    const int candidate =
                        vc_base + side * reserve + reserve_slot;
                    if (!side_units[side]->is_vc_idle(candidate))
                        reserve_busy[side]++;
                }
            }

            const int peer_side = 1 - owner_side;
            // A blocked peer overrides stickiness.  Otherwise move the
            // credit only toward strictly greater reserved pressure; ties
            // keep the last owner to avoid ownership ping-pong.
            if ((free_slots[peer_side] == 0 &&
                 free_slots[owner_side] > 0) ||
                reserve_busy[peer_side] > reserve_busy[owner_side]) {
                target_side = peer_side;
            }
        } else if (free_slots[0] == 0 && free_slots[1] > 0) {
            target_side = 0;
        } else if (free_slots[1] == 0 && free_slots[0] > 0) {
            target_side = 1;
        } else {
            target_side = m_router->dpphysTakeRrSide(pair, vnet);
        }
    }

    if (target_side != owner_side &&
        owner_count[target_side] >= net->dpphysCap()) {
        target_side = owner_side;
    }

    if (target_side != owner_side) {
        target = m_router->getPairedInputUnit(owner_inport);
        m_router->setDpphysPoolOwner(
            pair, vnet, pool_slot, target_side);
        net->incrementDpphysGrantsMigrated();
        owner_count[owner_side]--;
        owner_count[target_side]++;
    }

    assert(owner_count[0] + owner_count[1] == net->dpphysP());
    assert(owner_count[0] <= net->dpphysCap());
    assert(owner_count[1] <= net->dpphysCap());
    const int half = net->dpphysP() / 2;
    net->updateDpphysBorrowedPeak(
        std::max(std::max(0, owner_count[0] - half),
                 std::max(0, owner_count[1] - half)));
    target->increment_credit(vc, true, curTick());
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
            output_available = output_unit->has_free_vc_class(
                vnet, escape_request);
            if (!output_available &&
                m_router->get_net_ptr()->isDPPhys() &&
                output_unit->get_direction() != "Local" &&
                !escape_request) {
                m_router->get_net_ptr()->incrementDpphysPoolFullBlock();
            }
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
        outvc = m_router->getOutputUnit(outport)->select_free_vc_class(
            vnet, escape_request);
    } else {
        bool wormhole_control = m_router->get_net_ptr()->isWormhole() &&
            m_router->get_net_ptr()->get_vnet_type(vnet) == CTRL_VNET_;
        outvc = m_router->getOutputUnit(outport)->select_vc(
            vnet, wormhole_control);
    }

    // has to get a valid VC since it checked before performing SA
    assert(outvc != -1);
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
    std::fill(m_escape_requests.begin(), m_escape_requests.end(), false);
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
