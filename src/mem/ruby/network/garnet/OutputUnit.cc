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


#include "mem/ruby/network/garnet/OutputUnit.hh"

#include <algorithm>

#include "debug/RubyNetwork.hh"
#include "mem/ruby/network/garnet/Credit.hh"
#include "mem/ruby/network/garnet/CreditLink.hh"
#include "mem/ruby/network/garnet/GarnetNetwork.hh"
#include "mem/ruby/network/garnet/InputUnit.hh"
#include "mem/ruby/network/garnet/Router.hh"
#include "mem/ruby/network/garnet/flitBuffer.hh"

namespace gem5
{

namespace ruby
{

namespace garnet
{

OutputUnit::OutputUnit(int id, PortDirection direction, Router *router,
  uint32_t consumerVcs)
  : Consumer(router), m_router(router), m_id(id), m_direction(direction),
    m_vc_per_vnet(consumerVcs)
{
    const int m_num_vcs = consumerVcs * m_router->get_num_vnets();
    outVcState.reserve(m_num_vcs);
    for (int i = 0; i < m_num_vcs; i++) {
        outVcState.emplace_back(i, m_router->get_net_ptr(), consumerVcs);
    }
    m_dpphys_return_wait.assign(m_router->get_num_vnets(), 0);

    auto *net = m_router->get_net_ptr();
    if (net->isDPPhys() && m_direction != "Local") {
        const int side =
            GarnetNetwork::dpphysSideOfOutportDirn(m_direction);
        assert(side >= 0);
        for (int vc = 0; vc < m_num_vcs; ++vc) {
            const int offset = vc % m_vc_per_vnet;
            if (!net->dpphysOffsetAllowedAt(offset, side)) {
                while (outVcState[vc].get_credit_count() > 0)
                    outVcState[vc].decrement_credit();
            }
        }
    }
}

void
OutputUnit::decrement_credit(int out_vc)
{
    DPRINTF(RubyNetwork, "Router %d OutputUnit %s decrementing credit:%d for "
            "outvc %d at time: %lld for %s\n", m_router->get_id(),
            m_router->getPortDirectionName(get_direction()),
            outVcState[out_vc].get_credit_count(),
            out_vc, m_router->curCycle(), m_credit_link->name());

    outVcState[out_vc].decrement_credit();
}

void
OutputUnit::increment_credit(int out_vc)
{
    DPRINTF(RubyNetwork, "Router %d OutputUnit %s incrementing credit:%d for "
            "outvc %d at time: %lld from:%s\n", m_router->get_id(),
            m_router->getPortDirectionName(get_direction()),
            outVcState[out_vc].get_credit_count(),
            out_vc, m_router->curCycle(), m_credit_link->name());

    outVcState[out_vc].increment_credit();
}

// Check if the output VC (i.e., input VC at next router)
// has free credits (i..e, buffer slots).
// This is tracked by OutVcState
bool
OutputUnit::has_credit(int out_vc)
{
    assert(outVcState[out_vc].isInState(ACTIVE_, curTick()));
    return outVcState[out_vc].has_credit();
}


// Check if the output port (i.e., input port at next router) has free VCs.
bool
OutputUnit::has_free_vc(int vnet)
{
    return has_free_vc(vnet, 0, m_vc_per_vnet);
}

bool
OutputUnit::has_free_vc(int vnet, int first_offset, int count)
{
    return free_vc_credit_count(vnet, first_offset, count) > 0;
}

int
OutputUnit::free_vc_credit_count(int vnet, int first_offset, int count)
{
    assert(first_offset >= 0 && count > 0);
    assert(first_offset + count <= m_vc_per_vnet);

    int credits = 0;
    const int vc_base = vnet * m_vc_per_vnet;
    for (int offset = first_offset; offset < first_offset + count; offset++) {
        const int vc = vc_base + offset;
        if (is_vc_idle(vc, curTick()))
            credits += outVcState[vc].get_credit_count();
    }

    return credits;
}

// DP-Phys: the VC ids this port may use for one class, in
// availability order (own reserve first, then the side's pool half).
std::vector<int>
OutputUnit::dpphys_offsets(bool escape)
{
    auto *net = m_router->get_net_ptr();
    const bool local = m_direction == "Local";
    const int side = local ? 0 :
        GarnetNetwork::dpphysSideOfOutportDirn(m_direction);
    return net->dpphysOrderedOffsets(escape, side, local);
}

// Class-based selectors: resolve this port's VC layout (baseline
// contiguous windows, or the DP-Phys pair-global id space) and visit
// the class members in availability order.
bool
OutputUnit::has_free_vc_class(int vnet, bool escape)
{
    return free_vc_credit_count_class(vnet, escape) > 0;
}

int
OutputUnit::free_vc_credit_count_class(int vnet, bool escape)
{
    auto *net = m_router->get_net_ptr();
    if (!net->isDPPhys()) {
        const auto window = escape ? net->escapeWindow()
                                   : net->adaptiveWindow();
        return free_vc_credit_count(vnet, window.first, window.second);
    }

    int credits = 0;
    const int vc_base = vnet * m_vc_per_vnet;
    for (const int offset : dpphys_offsets(escape)) {
        const int vc = vc_base + offset;
        if (is_vc_idle(vc, curTick()))
            credits += outVcState[vc].get_credit_count();
    }
    return credits;
}

int
OutputUnit::select_free_vc_class(int vnet, bool escape)
{
    auto *net = m_router->get_net_ptr();
    if (!net->isDPPhys()) {
        const auto window = escape ? net->escapeWindow()
                                   : net->adaptiveWindow();
        return select_free_vc(vnet, window.first, window.second);
    }

    const int vc_base = vnet * m_vc_per_vnet;
    for (const int offset : dpphys_offsets(escape)) {
        const int vc = vc_base + offset;
        if (is_vc_idle(vc, curTick()) &&
            outVcState[vc].get_credit_count() > 0) {
            outVcState[vc].setState(ACTIVE_, curTick());
            return vc;
        }
    }
    return -1;
}

// Number of idle (free) VCs of this vnet at the downstream input port.
// Used by the Critical Bubble Scheme to reserve the critical slot.
int
OutputUnit::count_free_vcs(int vnet)
{
    int free_vcs = 0;
    const int vc_base = vnet * m_vc_per_vnet;
    for (int vc = vc_base; vc < vc_base + m_vc_per_vnet; vc++) {
        if (is_vc_idle(vc, curTick()))
            free_vcs++;
    }

    return free_vcs;
}

bool
OutputUnit::has_credit_vc(int vnet)
{
    int vc_base = vnet*m_vc_per_vnet;
    for (int vc = vc_base; vc < vc_base + m_vc_per_vnet; vc++) {
        if (outVcState[vc].has_credit())
            return true;
    }

    return false;
}

// Assign a free output VC to the winner of Switch Allocation
int
OutputUnit::select_free_vc(int vnet)
{
    return select_free_vc(vnet, 0, m_vc_per_vnet);
}

int
OutputUnit::select_free_vc(int vnet, int first_offset, int count)
{
    assert(first_offset >= 0 && count > 0);
    assert(first_offset + count <= m_vc_per_vnet);

    const int vc_base = vnet * m_vc_per_vnet;
    for (int offset = first_offset; offset < first_offset + count; offset++) {
        const int vc = vc_base + offset;
        if (is_vc_idle(vc, curTick())) {
            outVcState[vc].setState(ACTIVE_, curTick());
            return vc;
        }
    }

    return -1;
}

int
OutputUnit::select_vc(int vnet, bool allow_active)
{
    int vc_base = vnet*m_vc_per_vnet;
    for (int vc = vc_base; vc < vc_base + m_vc_per_vnet; vc++) {
        bool idle = is_vc_idle(vc, curTick());
        if (idle || (allow_active && outVcState[vc].has_credit())) {
            outVcState[vc].setState(ACTIVE_, curTick());
            return vc;
        }
    }

    return -1;
}

/*
 * The wakeup function of the OutputUnit reads the credit signal from the
 * downstream router for the output VC (i.e., input VC at downstream router).
 * It increments the credit count in the appropriate output VC state.
 * If the credit carries is_free_signal as true,
 * the output VC is marked IDLE.
 */

void
OutputUnit::wakeup()
{
    if (m_credit_link->isReady(curTick())) {
        Credit *t_credit = (Credit*) m_credit_link->consumeLink();
        if (t_credit->is_return()) {
            assert(m_router->get_net_ptr()->dpphysPolicy() == "starve");
            m_router->handleDpphysReturn(
                m_direction, t_credit->get_vc());
        } else {
            increment_credit(t_credit->get_vc());

            if (t_credit->is_free_signal())
                set_vc_state(IDLE_, t_credit->get_vc(), curTick());
        }

        delete t_credit;

        if (m_credit_link->isReady(curTick())) {
            scheduleEvent(Cycles(1));
        }
    }
}

bool
OutputUnit::tryDpphysReturn()
{
    auto *net = m_router->get_net_ptr();
    if (net->dpphysPolicy() != "starve" || m_direction == "Local")
        return false;

    bool needs_wakeup = false;
    bool returned = false;
    const int pool_begin = 2 * net->dpphysR();
    const int pool_end = pool_begin + net->dpphysP();
    const int link_latency = m_credit_link->getLatency();
    const int rtt = 2 * link_latency + 1;

    for (int vnet = 0; vnet < m_router->get_num_vnets(); ++vnet) {
        // The pair-global design transfers one whole single-slot VC with
        // one credit.  The evaluation injects on the control vnet.
        if (net->get_vnet_type(vnet) != CTRL_VNET_) {
            m_dpphys_return_wait[vnet] = 0;
            continue;
        }

        int credits_held = 0;
        int return_vc = -1;
        const int vc_base = vnet * m_vc_per_vnet;
        for (int offset = pool_begin; offset < pool_end; ++offset) {
            const int vc = vc_base + offset;
            if (is_vc_idle(vc, curTick()) &&
                outVcState[vc].get_credit_count() > 0) {
                credits_held++;
                return_vc = vc;
            }
        }

        const int flits_queued = m_router->countFlitsFor(m_id, vnet);
        if (credits_held == 0 || credits_held <= flits_queued) {
            m_dpphys_return_wait[vnet] = 0;
            continue;
        }

        const int threshold = credits_held >= 2 ?
            std::max(1, rtt / 4) : 2 * rtt;
        m_dpphys_return_wait[vnet]++;
        if (!returned && m_dpphys_return_wait[vnet] >= threshold) {
            assert(return_vc >= 0);
            decrement_credit(return_vc);
            m_router->getInputUnitByDirection(m_direction)->
                enqueueDpphysReturn(return_vc, curTick());
            net->incrementDpphysCreditReturned();
            m_dpphys_return_wait[vnet] = 0;
            returned = true;
            credits_held--;
        }
        if (credits_held > flits_queued)
            needs_wakeup = true;
    }

    return needs_wakeup;
}

flitBuffer*
OutputUnit::getOutQueue()
{
    return &outBuffer;
}

void
OutputUnit::set_out_link(NetworkLink *link)
{
    m_out_link = link;
}

void
OutputUnit::set_credit_link(CreditLink *credit_link)
{
    m_credit_link = credit_link;
}

void
OutputUnit::insert_flit(flit *t_flit)
{
    outBuffer.insert(t_flit);
    m_out_link->scheduleEventAbsolute(m_router->clockEdge(Cycles(1)));
}

bool
OutputUnit::functionalRead(Packet *pkt, WriteMask &mask)
{
    return outBuffer.functionalRead(pkt, mask);
}

uint32_t
OutputUnit::functionalWrite(Packet *pkt)
{
    return outBuffer.functionalWrite(pkt);
}

} // namespace garnet
} // namespace ruby
} // namespace gem5
