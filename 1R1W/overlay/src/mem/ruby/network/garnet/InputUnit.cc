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


#include "mem/ruby/network/garnet/InputUnit.hh"

#include "debug/RubyNetwork.hh"
#include "mem/ruby/network/garnet/Credit.hh"
#include "mem/ruby/network/garnet/GarnetNetwork.hh"
#include "mem/ruby/network/garnet/Router.hh"

namespace gem5
{

namespace ruby
{

namespace garnet
{

InputUnit::InputUnit(int id, PortDirection direction, Router *router)
  : Consumer(router), m_router(router), m_id(id), m_direction(direction),
    m_vc_per_vnet(m_router->get_vc_per_vnet())
{
    const int m_num_vcs = m_router->get_num_vcs();
    m_num_buffer_reads.resize(m_num_vcs/m_vc_per_vnet);
    m_num_buffer_writes.resize(m_num_vcs/m_vc_per_vnet);
    for (int i = 0; i < m_num_buffer_reads.size(); i++) {
        m_num_buffer_reads[i] = 0;
        m_num_buffer_writes[i] = 0;
    }

    // Instantiating the virtual channels
    virtualChannels.reserve(m_num_vcs);
    for (int i=0; i < m_num_vcs; i++) {
        virtualChannels.emplace_back();
    }
}

/*
 * The InputUnit wakeup function reads the input flit from its input link.
 * Each flit arrives with an input VC.
 * For HEAD/HEAD_TAIL flits, performs route computation,
 * and updates route in the input VC.
 * The flit is buffered for (m_latency - 1) cycles in the input VC
 * and marked as valid for SwitchAllocation starting that cycle.
 *
 */

void
InputUnit::wakeup()
{
    if (m_in_link->isReady(curTick())) {
        flit *t_flit = m_in_link->consumeLink();
        DPRINTF(RubyNetwork, "Router[%d] Consuming:%s Width: %d Flit:%s\n",
                m_router->get_id(), m_in_link->name(),
                m_router->getBitWidth(), *t_flit);
        assert(t_flit->m_width == m_router->getBitWidth());
        t_flit->increment_hops(); // for stats

        const int upstream_vc = t_flit->get_vc();
        int physical_vc = upstream_vc;
        InputUnit *target = this;
        PortDirection target_direction = m_direction;
        auto *net = m_router->get_net_ptr();

        // Internal DP-Phys links expose a logical namespace containing all
        // four pool slots. Map that namespace back onto the fixed four-slot
        // physical layout, redirecting borrowed slots to the InputUnit that
        // physically owns the selected pool entry.
        if (net->isDPPhysEnabled() && m_direction != "Local") {
            const int logical_vcs = net->getDPPhysLogicalVCs();
            const int vnet = t_flit->get_vnet();
            assert(upstream_vc / logical_vcs == vnet);
            const int logical_offset = upstream_vc % logical_vcs;
            int physical_offset = logical_offset;
            if (net->dpPhysGoverns(vnet, m_direction)) {
                net->dpPhysMapLogicalVC(
                    m_router->get_id(), m_direction, vnet, logical_offset,
                    target_direction, physical_offset);
            } else {
                // Data vnets use the ordinary physical VC offsets; only the
                // per-vnet stride on the internal link is enlarged.
                assert(logical_offset < m_vc_per_vnet);
            }
            target = m_router->getInputUnitByDirection(target_direction);
            physical_vc = vnet * m_vc_per_vnet + physical_offset;
        }

        target->accept_flit(t_flit, physical_vc, m_direction, m_id,
                            upstream_vc);

        if (m_in_link->isReady(curTick()))
            m_router->schedule_wakeup(Cycles(1));
    }
}

void
InputUnit::accept_flit(flit *t_flit, int vc,
                       const PortDirection &true_direction,
                       int credit_inport, int upstream_vc)
{
    assert(vc >= 0 && vc < static_cast<int>(virtualChannels.size()));
    const int vnet = t_flit->get_vnet();
    assert(vc / m_vc_per_vnet == vnet);
    const bool is_head = t_flit->get_type() == HEAD_ ||
                         t_flit->get_type() == HEAD_TAIL_;
    const bool wormhole_control = m_router->get_net_ptr()->isWormhole() &&
        m_router->get_net_ptr()->get_vnet_type(vnet) == CTRL_VNET_;

    if (is_head) {
        const bool idle = virtualChannels[vc].get_state() == IDLE_;
        assert(idle || wormhole_control);
        if (idle) {
            virtualChannels[vc].set_ingress_metadata(
                credit_inport, upstream_vc, true_direction);
            set_vc_active(vc, curTick());
        } else {
            virtualChannels[vc].set_enqueue_time(curTick());
        }

        const int outport = m_router->route_compute(
            t_flit->get_route(), m_id, true_direction, vc);
        if (wormhole_control)
            t_flit->set_outport(outport);
        else
            grant_outport(vc, outport);
    } else {
        assert(virtualChannels[vc].get_state() == ACTIVE_);
    }

    // From this point onward the router indexes the physical VC.
    t_flit->set_vc(vc);
    virtualChannels[vc].insertFlit(t_flit);

    // number of writes same as reads: every buffered flit is read once.
    m_num_buffer_writes[vnet]++;
    m_num_buffer_reads[vnet]++;

    const Cycles pipe_stages = m_router->get_pipe_stages();
    if (pipe_stages == 1) {
        t_flit->advance_stage(SA_, curTick());
    } else {
        assert(pipe_stages > 1);
        const Cycles wait_time = pipe_stages - Cycles(1);
        t_flit->advance_stage(SA_, m_router->clockEdge(wait_time));
        m_router->schedule_wakeup(wait_time);
    }
}

int
InputUnit::count_active_vcs(int vnet, int first_offset, int count) const
{
    assert(first_offset >= 0 && count >= 0);
    assert(first_offset + count <= m_vc_per_vnet);
    int active = 0;
    const int base = vnet * m_vc_per_vnet;
    for (int offset = first_offset; offset < first_offset + count; ++offset) {
        if (virtualChannels[base + offset].get_state() != IDLE_)
            active++;
    }
    return active;
}

// Send a credit back to upstream router for this VC.
// Called by SwitchAllocator when the flit in this VC wins the Switch.
void
InputUnit::increment_credit(int in_vc, bool free_signal, Tick curTime)
{
    int credit_inport = m_id;
    int upstream_vc = in_vc;
    auto *net = m_router->get_net_ptr();
    if (net->isDPPhysEnabled() &&
        virtualChannels[in_vc].get_credit_inport() >= 0) {
        credit_inport = virtualChannels[in_vc].get_credit_inport();
        upstream_vc = virtualChannels[in_vc].get_upstream_vc();
        if (free_signal) {
            const int vnet = in_vc / m_vc_per_vnet;
            net->dpPhysNoteFree(
                m_router->get_id(),
                virtualChannels[in_vc].get_true_direction(), vnet,
                upstream_vc % net->getDPPhysLogicalVCs());
        }
    }
    m_router->getInputUnit(credit_inport)->enqueue_credit(
        upstream_vc, free_signal, curTime);
}

void
InputUnit::enqueue_credit(int upstream_vc, bool free_signal, Tick curTime)
{
    DPRINTF(RubyNetwork, "Router[%d]: Sending a credit vc:%d free:%d to %s\n",
            m_router->get_id(), upstream_vc, free_signal,
            m_credit_link->name());
    Credit *t_credit = new Credit(upstream_vc, free_signal, curTime);
    creditQueue.insert(t_credit);
    m_credit_link->scheduleEventAbsolute(m_router->clockEdge(Cycles(1)));
}

bool
InputUnit::functionalRead(Packet *pkt, WriteMask &mask)
{
    bool read = false;
    for (auto& virtual_channel : virtualChannels) {
        if (virtual_channel.functionalRead(pkt, mask))
            read = true;
    }

    return read;
}

uint32_t
InputUnit::functionalWrite(Packet *pkt)
{
    uint32_t num_functional_writes = 0;
    for (auto& virtual_channel : virtualChannels) {
        num_functional_writes += virtual_channel.functionalWrite(pkt);
    }

    return num_functional_writes;
}

void
InputUnit::resetStats()
{
    for (int j = 0; j < m_num_buffer_reads.size(); j++) {
        m_num_buffer_reads[j] = 0;
        m_num_buffer_writes[j] = 0;
    }
}

} // namespace garnet
} // namespace ruby
} // namespace gem5
