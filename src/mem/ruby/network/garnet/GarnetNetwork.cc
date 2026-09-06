/*
 * Copyright (c) 2020 Advanced Micro Devices, Inc.
 * Copyright (c) 2008 Princeton University
 * Copyright (c) 2016 Georgia Institute of Technology
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


#include "mem/ruby/network/garnet/GarnetNetwork.hh"

#include <cassert>
#include <limits>

#include "base/cast.hh"
#include "base/compiler.hh"
#include "debug/DPPhys.hh"
#include "debug/RubyNetwork.hh"
#include "mem/ruby/common/NetDest.hh"
#include "mem/ruby/network/MessageBuffer.hh"
#include "mem/ruby/network/garnet/CommonTypes.hh"
#include "mem/ruby/network/garnet/CreditLink.hh"
#include "mem/ruby/network/garnet/GarnetLink.hh"
#include "mem/ruby/network/garnet/InputUnit.hh"
#include "mem/ruby/network/garnet/NetworkInterface.hh"
#include "mem/ruby/network/garnet/NetworkLink.hh"
#include "mem/ruby/network/garnet/Router.hh"
#include "mem/ruby/system/RubySystem.hh"

namespace gem5
{

namespace ruby
{

namespace garnet
{

/*
 * GarnetNetwork sets up the routers and links and collects stats.
 * Default parameters (GarnetNetwork.py) can be overwritten from command line
 * (see configs/network/Network.py)
 */

GarnetNetwork::GarnetNetwork(const Params &p)
    : Network(p)
{
    m_num_rows = p.num_rows;
    m_torus_x = p.torus_x;
    m_torus_y = p.torus_y;
    m_torus_z = p.torus_z;
    m_ni_flit_size = p.ni_flit_size;
    m_max_vcs_per_vnet = 0;
    m_max_link_vcs_per_vnet = 0;
    m_escape_vcs = p.escape_vcs;
    m_buffers_per_data_vc = p.buffers_per_data_vc;
    m_buffers_per_ctrl_vc = p.buffers_per_ctrl_vc;
    m_wormhole = p.wormhole;
    m_enable_cbs = p.enable_cbs;
    m_enable_dp = p.enable_dp;
    m_dp_reserve = p.dp_reserve;
    m_dp_shared_cap = p.dp_shared_cap;
    m_enable_dpphys = p.enable_dpphys;
    m_dpphys_private_vcs = p.dpphys_private_vcs;
    m_dpphys_pool_vcs = p.dpphys_pool_vcs;
    m_dpphys_owner_cap = p.dpphys_owner_cap;
    m_dpphys_policy = p.dpphys_policy;
    m_dpphys_borrowed_peak_value = 0;
    m_dpphys_ownership_wait_max_value = 0;
    m_routing_algorithm = p.routing_algorithm;
    m_next_packet_id = 0;

    m_enable_fault_model = p.enable_fault_model;
    if (m_enable_fault_model)
        fault_model = p.fault_model;

    m_vnet_type.resize(m_virtual_networks);

    for (int i = 0 ; i < m_virtual_networks ; i++) {
        if (m_vnet_type_names[i] == "response")
            m_vnet_type[i] = DATA_VNET_; // carries data (and ctrl) packets
        else
            m_vnet_type[i] = CTRL_VNET_; // carries only ctrl packets
    }

    // record the routers
    for (std::vector<BasicRouter*>::const_iterator i =  p.routers.begin();
         i != p.routers.end(); ++i) {
        Router* router = safe_cast<Router*>(*i);
        m_routers.push_back(router);

        // initialize the router's network pointers
        router->init_net_ptr(this);
    }

    // record the network interfaces
    for (std::vector<ClockedObject*>::const_iterator i = p.netifs.begin();
         i != p.netifs.end(); ++i) {
        NetworkInterface *ni = safe_cast<NetworkInterface *>(*i);
        m_nis.push_back(ni);
        ni->init_net_ptr(this);
    }

    // Print Garnet version
    inform("Garnet version %s\n", garnetVersion);
}

void
GarnetNetwork::init()
{
    Network::init();

    for (int i=0; i < m_nodes; i++) {
        m_nis[i]->addNode(m_toNetQueues[i], m_fromNetQueues[i]);
    }

    // The topology pointer should have already been initialized in the
    // parent network constructor
    assert(m_topology_ptr != NULL);
    m_topology_ptr->createLinks(this);

    const uint64_t torus_routers =
        static_cast<uint64_t>(m_torus_x) * m_torus_y * m_torus_z;
    if (torus_routers > 0) {
        fatal_if(m_torus_x < 2 || m_torus_y < 2 || m_torus_z < 2,
            "All Torus3D dimensions must contain at least two routers");
        fatal_if(torus_routers != m_routers.size(),
            "Torus3D dimensions describe %llu routers, but the network "
            "contains %d", torus_routers, m_routers.size());
    }
    fatal_if(isTorus3DAdaptive() && torus_routers == 0,
        "Torus3D adaptive routing requires nonzero --torus-x/y/z");
    fatal_if(isTorus3DAdaptive() &&
             m_escape_vcs >= m_max_vcs_per_vnet,
        "Torus3D adaptive routing requires at least one adaptive VC per "
        "vnet; --escape-vcs must be smaller than --vcs-per-vnet");
    fatal_if(isTorus3DAdaptive() && isWormhole(),
        "Torus3D adaptive routing cannot be combined with --wormhole");
    fatal_if(m_enable_cbs && m_routing_algorithm != TORUS_3D_DOR_,
        "--enable-cbs requires Torus3D DOR routing "
        "(--routing-algorithm=3)");
    fatal_if(m_enable_cbs && torus_routers == 0,
        "--enable-cbs requires nonzero --torus-x/y/z");
    fatal_if(m_enable_cbs && isWormhole(),
        "--enable-cbs cannot be combined with --wormhole");
    fatal_if(m_enable_cbs && m_max_vcs_per_vnet < 2,
        "--enable-cbs requires at least 2 VCs per vnet: ring entry next "
        "to the critical bubble needs two free slots to ever proceed");
    if (m_enable_cbs)
        cbsInit();

    if (m_enable_dp) {
        fatal_if(torus_routers == 0,
            "--enable-dp requires nonzero --torus-x/y/z");
        fatal_if(m_torus_x < 3 || m_torus_y < 3 || m_torus_z < 3,
            "--enable-dp requires torus dimensions >= 3: in a dimension "
            "of size 2 both outports of a router lead to the same "
            "downstream pool, and same-cycle grants could overrun the "
            "cap");
        fatal_if(isWormhole(),
            "--enable-dp cannot be combined with --wormhole");
        fatal_if(m_routing_algorithm != TORUS_3D_DOR_ &&
                 m_routing_algorithm != TORUS_3D_ADAPTIVE_,
            "--enable-dp requires Torus3D routing (--routing-algorithm=3 "
            "with --enable-cbs, or --routing-algorithm=4)");
        if (m_routing_algorithm == TORUS_3D_DOR_) {
            fatal_if(!m_enable_cbs,
                "--enable-dp on routing-algorithm 3 requires --enable-cbs: "
                "the dedicated VCs run CBS as the deadlock-free substrate");
            fatal_if(m_dp_reserve < 2,
                "--enable-dp requires --dp-reserve >= 2: the dedicated "
                "sub-ring runs CBS, which needs two slots per inport");
            fatal_if(m_max_vcs_per_vnet <= m_dp_reserve,
                "--enable-dp requires --vcs-per-vnet > --dp-reserve so at "
                "least one pooled VC exists per inport");
        } else {
            fatal_if(m_escape_vcs < 1,
                "--enable-dp on routing-algorithm 4 requires "
                "--escape-vcs >= 1: the Mesh3D escape VCs are the "
                "deadlock-free substrate and stay exempt from the pool");
        }
        const uint32_t pooled_per_inport =
            (m_routing_algorithm == TORUS_3D_DOR_) ?
                m_max_vcs_per_vnet - m_dp_reserve :
                m_max_vcs_per_vnet - m_escape_vcs;
        const uint32_t max_pool_cap = 2 * pooled_per_inport;
        fatal_if(m_dp_shared_cap < 1 ||
                 m_dp_shared_cap > max_pool_cap,
            "--dp-shared-cap must lie in [1, %u]; a cap of %u pools "
            "nothing or exceeds the dimension-pair storage",
            max_pool_cap, m_dp_shared_cap);
        dpInit();
    }

    if (m_enable_dpphys) {
        fatal_if(m_enable_dp,
            "--enable-dpphys and --enable-dp are mutually exclusive");
        fatal_if(torus_routers == 0 || m_torus_x < 3 || m_torus_y < 3 ||
                 m_torus_z < 3,
            "--enable-dpphys requires Torus3D dimensions >= 3");
        fatal_if(m_routing_algorithm != TORUS_3D_ADAPTIVE_,
            "--enable-dpphys requires adaptive Torus3D routing "
            "(--routing-algorithm=4)");
        fatal_if(m_enable_cbs || m_wormhole,
            "--enable-dpphys cannot be combined with CBS or wormhole mode");
        fatal_if(m_escape_vcs < 1,
            "--enable-dpphys requires at least one private escape VC");
        fatal_if(m_dpphys_private_vcs < 1 ||
                 m_dpphys_pool_vcs < 2 || m_dpphys_pool_vcs % 2 != 0,
            "DP-Phys requires at least one private adaptive VC and a "
            "positive even pool size");
        const uint32_t expected_physical = m_dpphys_private_vcs +
            m_dpphys_pool_vcs / 2 + m_escape_vcs;
        const uint32_t reserved_vcs =
            m_dpphys_private_vcs + m_escape_vcs;
        fatal_if(reserved_vcs != m_dpphys_pool_vcs / 2,
            "DP-Phys phase RR requires private + escape (%u) to equal "
            "half of the pool (%u)", reserved_vcs,
            m_dpphys_pool_vcs / 2);
        fatal_if(m_max_vcs_per_vnet != expected_physical,
            "DP-Phys physical layout requires --vcs-per-vnet=%u "
            "(private %u + local pool half %u + escape %u), got %u",
            expected_physical, m_dpphys_private_vcs,
            m_dpphys_pool_vcs / 2, m_escape_vcs,
            m_max_vcs_per_vnet);
        fatal_if(m_buffers_per_ctrl_vc != 1,
            "DP-Phys currently requires one-flit control VC storage");
        fatal_if(m_dpphys_owner_cap < m_dpphys_pool_vcs / 2 ||
                 m_dpphys_owner_cap > m_dpphys_pool_vcs,
            "--dpphys-owner-cap must lie in [%u, %u]",
            m_dpphys_pool_vcs / 2, m_dpphys_pool_vcs);
        fatal_if(m_dpphys_policy != "rts" &&
                 m_dpphys_policy != "rr" &&
                 m_dpphys_policy != "pressure",
            "--dpphys-policy must be rts, rr, or pressure, got '%s'",
            m_dpphys_policy);
        dpPhysInit();
    }

    // Initialize topology specific parameters
    if (getNumRows() > 0) {
        // Only for Mesh topology
        // m_num_rows and m_num_cols are only used for
        // implementing XY or custom routing in RoutingUnit.cc
        m_num_rows = getNumRows();
        m_num_cols = m_routers.size() / m_num_rows;
        assert(m_num_rows * m_num_cols == m_routers.size());
    } else {
        m_num_rows = -1;
        m_num_cols = -1;
    }

    // FaultModel: declare each router to the fault model
    if (isFaultModelEnabled()) {
        for (std::vector<Router*>::const_iterator i= m_routers.begin();
             i != m_routers.end(); ++i) {
            Router* router = safe_cast<Router*>(*i);
            [[maybe_unused]] int router_id =
                fault_model->declare_router(router->get_num_inports(),
                                            router->get_num_outports(),
                                            router->get_vc_per_vnet(),
                                            getBuffersPerDataVC(),
                                            getBuffersPerCtrlVC());
            assert(router_id == router->get_id());
            router->printAggregateFaultProbability(std::cout);
            router->printFaultVector(std::cout);
        }
    }
}

/*
 * Critical Bubble Scheme (CBS) support. One buffer slot per directed torus
 * ring per vnet is marked "critical"; packets entering a ring may never
 * consume it, packets travelling along the ring may displace it upstream.
 * On ctrl vnets (single-flit packets, one buffer per VC) a slot is exactly
 * one VC, so the mark is tracked per (router, inport direction, vnet).
 */

int
GarnetNetwork::cbsDirnIndex(const PortDirection &dirn)
{
    if (dirn == "East") return 0;
    if (dirn == "West") return 1;
    if (dirn == "North") return 2;
    if (dirn == "South") return 3;
    if (dirn == "Up") return 4;
    if (dirn == "Down") return 5;
    return -1; // "Local" and unknown directions host no CBS mark
}

PortDirection
GarnetNetwork::cbsOppositeDirn(const PortDirection &dirn)
{
    if (dirn == "East") return "West";
    if (dirn == "West") return "East";
    if (dirn == "North") return "South";
    if (dirn == "South") return "North";
    if (dirn == "Up") return "Down";
    if (dirn == "Down") return "Up";
    panic("CBS: no opposite for port direction %s", dirn);
}

int
GarnetNetwork::cbsDownstreamRouter(int router_id,
                                   const PortDirection &outport_dirn) const
{
    const int X = m_torus_x;
    const int Y = m_torus_y;
    const int Z = m_torus_z;
    int x = router_id % X;
    int y = (router_id / X) % Y;
    int z = router_id / (X * Y);

    if (outport_dirn == "East") x = (x + 1) % X;
    else if (outport_dirn == "West") x = (x - 1 + X) % X;
    else if (outport_dirn == "North") y = (y + 1) % Y;
    else if (outport_dirn == "South") y = (y - 1 + Y) % Y;
    else if (outport_dirn == "Up") z = (z + 1) % Z;
    else if (outport_dirn == "Down") z = (z - 1 + Z) % Z;
    else panic("CBS: no downstream router across port %s", outport_dirn);

    return z * X * Y + y * X + x;
}

void
GarnetNetwork::cbsInit()
{
    const int X = m_torus_x;
    const int Y = m_torus_y;
    const int Z = m_torus_z;

    m_cbs_mark.assign(m_routers.size(),
        std::vector<std::vector<bool>>(6,
            std::vector<bool>(m_virtual_networks, false)));

    // Place one critical bubble per directed ring per vnet, at the ring's
    // coordinate-0 router. A packet moving in direction D arrives at the
    // downstream inport facing opposite(D).
    for (int vnet = 0; vnet < m_virtual_networks; vnet++) {
        for (int z = 0; z < Z; z++) {
            for (int y = 0; y < Y; y++) {
                int r = z * X * Y + y * X; // x = 0
                m_cbs_mark[r][cbsDirnIndex("West")][vnet] = true; // +X ring
                m_cbs_mark[r][cbsDirnIndex("East")][vnet] = true; // -X ring
            }
        }
        for (int z = 0; z < Z; z++) {
            for (int x = 0; x < X; x++) {
                int r = z * X * Y + x; // y = 0
                m_cbs_mark[r][cbsDirnIndex("South")][vnet] = true; // +Y ring
                m_cbs_mark[r][cbsDirnIndex("North")][vnet] = true; // -Y ring
            }
        }
        for (int y = 0; y < Y; y++) {
            for (int x = 0; x < X; x++) {
                int r = y * X + x; // z = 0
                m_cbs_mark[r][cbsDirnIndex("Down")][vnet] = true; // +Z ring
                m_cbs_mark[r][cbsDirnIndex("Up")][vnet] = true; // -Z ring
            }
        }
    }
}

bool
GarnetNetwork::cbsHasMark(int router_id, const PortDirection &inport_dirn,
                          int vnet) const
{
    int d = cbsDirnIndex(inport_dirn);
    if (d < 0)
        return false;
    return m_cbs_mark[router_id][d][vnet];
}

void
GarnetNetwork::cbsMoveMark(int from_router, const PortDirection &from_inport,
                           int to_router, const PortDirection &to_inport,
                           int vnet)
{
    int from_d = cbsDirnIndex(from_inport);
    int to_d = cbsDirnIndex(to_inport);
    assert(from_d >= 0 && to_d >= 0);
    assert(m_cbs_mark[from_router][from_d][vnet]);
    assert(!m_cbs_mark[to_router][to_d][vnet]);
    m_cbs_mark[from_router][from_d][vnet] = false;
    m_cbs_mark[to_router][to_d][vnet] = true;
    m_cbs_mark_moves++;
}

/*
 * Dimension Pool (DP) support. Pooled VCs of the two opposing inports of one
 * dimension form a joint pool. Admission is denied when the pair reaches its
 * cap.
 * Deadlock freedom never depends on the pool: the dedicated window
 * [0, dp_reserve) runs CBS on algorithm 3, the escape window on
 * algorithm 4 stays exempt. Occupancy is counted at allocation grant
 * (upstream reserves the slot) and released on the VC's free credit.
 */

bool
GarnetNetwork::dpPooledOffset(int vc_offset) const
{
    if (m_routing_algorithm == TORUS_3D_DOR_)
        return vc_offset >= static_cast<int>(m_dp_reserve);
    // Adaptive routing: the adaptive class [0, V - escape_vcs) is pooled,
    // the trailing escape VCs are exempt.
    return vc_offset <
        static_cast<int>(m_max_vcs_per_vnet - m_escape_vcs);
}

int
GarnetNetwork::dpSharedUsed(int router_id, const PortDirection &inport_dirn,
                            int vnet) const
{
    int d = cbsDirnIndex(inport_dirn);
    assert(d >= 0);
    return m_dp_shared_occ[router_id][d][vnet] +
           m_dp_shared_occ[router_id][d ^ 1][vnet];
}

bool
GarnetNetwork::dpPoolFull(int router_id, const PortDirection &inport_dirn,
                          int vnet) const
{
    if (cbsDirnIndex(inport_dirn) < 0)
        return false; // Local ports are not pooled
    return dpSharedUsed(router_id, inport_dirn, vnet) >=
        static_cast<int>(m_dp_shared_cap);
}

void
GarnetNetwork::dpNoteAlloc(int router_id, const PortDirection &inport_dirn,
                           int vnet, int vc_offset)
{
    int d = cbsDirnIndex(inport_dirn);
    if (d < 0 || !dpGoverns(vnet) || !dpPooledOffset(vc_offset))
        return;
    m_dp_shared_occ[router_id][d][vnet]++;
    m_dp_shared_grants++;
}

void
GarnetNetwork::dpNoteFree(int router_id, const PortDirection &inport_dirn,
                          int vnet, int vc_offset)
{
    int d = cbsDirnIndex(inport_dirn);
    if (d < 0 || !dpGoverns(vnet) || !dpPooledOffset(vc_offset))
        return;
    assert(m_dp_shared_occ[router_id][d][vnet] > 0);
    m_dp_shared_occ[router_id][d][vnet]--;
}

void
GarnetNetwork::dpInit()
{
    m_dp_shared_occ.assign(m_routers.size(),
        std::vector<std::vector<int>>(6,
            std::vector<int>(m_virtual_networks, 0)));
}

bool
GarnetNetwork::dpPhysGoverns(int vnet,
                             const PortDirection &direction) const
{
    return m_enable_dpphys && cbsDirnIndex(direction) >= 0 &&
           m_vnet_type[vnet] == CTRL_VNET_;
}

bool
GarnetNetwork::dpPhysPhysicalPooledOffset(int vc_offset) const
{
    return vc_offset >= static_cast<int>(m_dpphys_private_vcs) &&
           vc_offset < static_cast<int>(m_dpphys_private_vcs +
                                        m_dpphys_pool_vcs / 2);
}

void
GarnetNetwork::dpPhysMapLogicalVC(
    int router_id, const PortDirection &true_inport, int vnet,
    int logical_offset, PortDirection &physical_inport,
    int &physical_offset) const
{
    const int d = cbsDirnIndex(true_inport);
    assert(d >= 0 && router_id >= 0 && router_id < m_routers.size());
    const int pair = d / 2;
    const int side = d % 2;
    physical_inport = true_inport;

    if (logical_offset < static_cast<int>(m_dpphys_private_vcs)) {
        physical_offset = logical_offset;
        return;
    }

    const int pool_begin = m_dpphys_private_vcs;
    const int pool_end = pool_begin + m_dpphys_pool_vcs;
    if (logical_offset < pool_end) {
        const int slot = logical_offset - pool_begin;
        assert(m_dpphys_busy[router_id][pair][vnet][slot]);
        assert(m_dpphys_owner[router_id][pair][vnet][slot] == side);
        const int physical_side = slot / (m_dpphys_pool_vcs / 2);
        const int physical_dir = pair * 2 + physical_side;
        static const PortDirection directions[6] = {
            "East", "West", "North", "South", "Up", "Down"
        };
        physical_inport = directions[physical_dir];
        physical_offset = m_dpphys_private_vcs +
                          slot % (m_dpphys_pool_vcs / 2);
        return;
    }

    const int escape_offset = logical_offset - pool_end;
    assert(escape_offset >= 0 &&
           escape_offset < static_cast<int>(m_escape_vcs));
    physical_offset = m_dpphys_private_vcs + m_dpphys_pool_vcs / 2 +
                      escape_offset;
}

int
GarnetNetwork::dpPhysOwnerCount(int router_id, int pair, int vnet,
                                int side) const
{
    int count = 0;
    for (int owner : m_dpphys_owner[router_id][pair][vnet])
        count += owner == side;
    return count;
}

bool
GarnetNetwork::dpPhysSlotOwnedBy(
    int router_id, const PortDirection &inport_dirn, int vnet, int slot) const
{
    const int d = cbsDirnIndex(inport_dirn);
    assert(d >= 0 && slot >= 0 &&
           slot < static_cast<int>(m_dpphys_pool_vcs));
    return m_dpphys_owner[router_id][d / 2][vnet][slot] == d % 2;
}

bool
GarnetNetwork::dpPhysCanClaimSlot(
    int router_id, const PortDirection &inport_dirn, int vnet, int slot) const
{
    const int d = cbsDirnIndex(inport_dirn);
    assert(d >= 0 && slot >= 0 &&
           slot < static_cast<int>(m_dpphys_pool_vcs));
    const int pair = d / 2;
    const int side = d % 2;
    if (m_dpphys_busy[router_id][pair][vnet][slot])
        return false;
    if (m_dpphys_owner[router_id][pair][vnet][slot] == side)
        return true;
    return m_dpphys_policy == "pressure" &&
           dpPhysOwnerCount(router_id, pair, vnet, side) <
               static_cast<int>(m_dpphys_owner_cap);
}

bool
GarnetNetwork::dpPhysPoolWriteAvailable(
    int router_id, const PortDirection &inport_dirn, int vnet,
    Tick when) const
{
    const int d = cbsDirnIndex(inport_dirn);
    assert(d >= 0);
    return m_dpphys_write_tick[router_id][d / 2][vnet] != when;
}

void
GarnetNetwork::dpPhysSetOwner(int router_id, int pair, int vnet,
                              int slot, int side)
{
    int &owner = m_dpphys_owner[router_id][pair][vnet][slot];
    if (owner == side)
        return;
    owner = side;
    m_dpphys_owner_migrations++;
    m_dpphys_migrations_to_dir[pair * 2 + side]++;
    uint64_t &wait_start =
        m_dpphys_ownership_wait_start[router_id][pair][vnet][side];
    if (wait_start != std::numeric_limits<uint64_t>::max()) {
        const uint64_t delay =
            static_cast<uint64_t>(curCycle()) - wait_start;
        m_dpphys_ownership_wait_completions++;
        m_dpphys_ownership_wait_cycles += delay;
        if (delay > m_dpphys_ownership_wait_max_value) {
            m_dpphys_ownership_wait_max_value = delay;
            m_dpphys_ownership_wait_max = delay;
        }
        wait_start = std::numeric_limits<uint64_t>::max();
    }
    const int borrowed = dpPhysOwnerCount(router_id, pair, vnet, side) -
                         static_cast<int>(m_dpphys_pool_vcs / 2);
    if (borrowed > static_cast<int>(m_dpphys_borrowed_peak_value)) {
        m_dpphys_borrowed_peak_value = borrowed;
        m_dpphys_borrowed_peak = borrowed;
    }
}

bool
GarnetNetwork::dpPhysClaimSlot(
    int router_id, const PortDirection &inport_dirn, int vnet, int slot,
    Tick when)
{
    const int d = cbsDirnIndex(inport_dirn);
    assert(d >= 0);
    const int pair = d / 2;
    const int side = d % 2;
    if (!dpPhysPoolWriteAvailable(
            router_id, inport_dirn, vnet, when)) {
        m_dpphys_pool_write_blocks++;
        return false;
    }
    if (!dpPhysCanClaimSlot(router_id, inport_dirn, vnet, slot))
        return false;
    const bool demand_reclaim =
        m_dpphys_owner[router_id][pair][vnet][slot] != side;
    if (demand_reclaim) {
        dpPhysNoteOwnershipDemand(router_id, inport_dirn, vnet);
        DPRINTF(DPPhys, "owner-change tick=%llu cycle=%llu router=%d "
                "pair=%d vnet=%d slot=%d from=%d to=%d cause=demand\n",
                static_cast<unsigned long long>(curTick()),
                static_cast<unsigned long long>(curCycle()), router_id,
                pair, vnet, slot, side ^ 1, side);
    }
    dpPhysSetOwner(router_id, pair, vnet, slot, side);
    m_dpphys_busy[router_id][pair][vnet][slot] = true;
    m_dpphys_write_tick[router_id][pair][vnet] = when;
    m_dpphys_pool_allocations++;
    m_dpphys_pool_allocations_by_dir[d]++;
    if (demand_reclaim)
        m_dpphys_demand_reclaims++;
    else
        m_dpphys_owned_pool_allocations++;
    return true;
}

void
GarnetNetwork::dpPhysNoteOwnershipDemand(
    int router_id, const PortDirection &inport_dirn, int vnet)
{
    const int d = cbsDirnIndex(inport_dirn);
    assert(d >= 0);
    const int pair = d / 2;
    const int side = d % 2;
    if (dpPhysOwnerCount(router_id, pair, vnet, side) >=
        static_cast<int>(m_dpphys_owner_cap)) {
        return;
    }

    uint64_t &wait_start =
        m_dpphys_ownership_wait_start[router_id][pair][vnet][side];
    if (wait_start == std::numeric_limits<uint64_t>::max()) {
        wait_start = static_cast<uint64_t>(curCycle());
        m_dpphys_ownership_wait_starts++;
    }
}

int
GarnetNetwork::dpPhysReservedUsed(
    int router_id, const PortDirection &inport_dirn, int vnet) const
{
    auto *input = m_routers[router_id]->getInputUnitByDirection(inport_dirn);
    int used = input->count_active_vcs(vnet, 0, m_dpphys_private_vcs);
    const int escape_begin = m_dpphys_private_vcs +
                             m_dpphys_pool_vcs / 2;
    used += input->count_active_vcs(vnet, escape_begin, m_escape_vcs);
    return used;
}

void
GarnetNetwork::dpPhysNoteFree(
    int router_id, const PortDirection &true_inport, int vnet,
    int logical_offset)
{
    const int pool_begin = m_dpphys_private_vcs;
    const int slot = logical_offset - pool_begin;
    if (!dpPhysGoverns(vnet, true_inport) || slot < 0 ||
        slot >= static_cast<int>(m_dpphys_pool_vcs))
        return;

    const int d = cbsDirnIndex(true_inport);
    const int pair = d / 2;
    const int side = d % 2;
    assert(m_dpphys_busy[router_id][pair][vnet][slot]);
    assert(m_dpphys_owner[router_id][pair][vnet][slot] == side);
    m_dpphys_busy[router_id][pair][vnet][slot] = false;

    int target = side;
    if (m_dpphys_policy == "rr") {
        target = m_dpphys_rr_next[router_id][pair][vnet];
        m_dpphys_rr_next[router_id][pair][vnet] ^= 1;
    } else if (m_dpphys_policy == "pressure") {
        const int peer = side ^ 1;
        static const PortDirection directions[6] = {
            "East", "West", "North", "South", "Up", "Down"
        };
        const int own_pressure = dpPhysReservedUsed(
            router_id, directions[pair * 2 + side], vnet);
        const int peer_pressure = dpPhysReservedUsed(
            router_id, directions[pair * 2 + peer], vnet);
        // Equal pressure is deliberately sticky: a returning credit remains
        // with the last user, which preserves burst/packet locality.
        if (peer_pressure > own_pressure)
            target = peer;
    }

    if (target != side &&
        dpPhysOwnerCount(router_id, pair, vnet, target) >=
            static_cast<int>(m_dpphys_owner_cap))
        target = side;
    if (target == side)
        m_dpphys_release_keeps++;
    else {
        m_dpphys_release_handoffs++;
        DPRINTF(DPPhys, "owner-change tick=%llu cycle=%llu router=%d "
                "pair=%d vnet=%d slot=%d from=%d to=%d cause=release\n",
                static_cast<unsigned long long>(curTick()),
                static_cast<unsigned long long>(curCycle()), router_id,
                pair, vnet, slot, side, target);
    }
    dpPhysSetOwner(router_id, pair, vnet, slot, target);
}

void
GarnetNetwork::dpPhysInit()
{
    const int routers = m_routers.size();
    const int pairs = 3;
    m_dpphys_owner.assign(routers,
        std::vector<std::vector<std::vector<int>>>(pairs,
            std::vector<std::vector<int>>(m_virtual_networks,
                std::vector<int>(m_dpphys_pool_vcs, 0))));
    m_dpphys_busy.assign(routers,
        std::vector<std::vector<std::vector<bool>>>(pairs,
            std::vector<std::vector<bool>>(m_virtual_networks,
                std::vector<bool>(m_dpphys_pool_vcs, false))));
    m_dpphys_rr_next.assign(routers,
        std::vector<std::vector<int>>(pairs,
            std::vector<int>(m_virtual_networks, 0)));
    m_dpphys_write_tick.assign(routers,
        std::vector<std::vector<Tick>>(pairs,
            std::vector<Tick>(m_virtual_networks,
                std::numeric_limits<Tick>::max())));
    m_dpphys_ownership_wait_start.assign(routers,
        std::vector<std::vector<std::vector<uint64_t>>>(pairs,
            std::vector<std::vector<uint64_t>>(m_virtual_networks,
                std::vector<uint64_t>(
                    2, std::numeric_limits<uint64_t>::max()))));

    // Start at the private baseline: each direction owns the two pool
    // entries physically located in its own InputUnit.
    for (int router = 0; router < routers; ++router) {
        for (int pair = 0; pair < pairs; ++pair) {
            for (int vnet = 0; vnet < m_virtual_networks; ++vnet) {
                for (int slot = 0; slot < m_dpphys_pool_vcs; ++slot) {
                    m_dpphys_owner[router][pair][vnet][slot] =
                        slot / (m_dpphys_pool_vcs / 2);
                }
            }
        }
    }
}

/*
 * This function creates a link from the Network Interface (NI)
 * into the Network.
 * It creates a Network Link from the NI to a Router and a Credit Link from
 * the Router to the NI
*/

void
GarnetNetwork::makeExtInLink(NodeID global_src, SwitchID dest, BasicLink* link,
                             std::vector<NetDest>& routing_table_entry)
{
    NodeID local_src = getLocalNodeID(global_src);
    assert(local_src < m_nodes);

    GarnetExtLink* garnet_link = safe_cast<GarnetExtLink*>(link);

    // GarnetExtLink is bi-directional
    NetworkLink* net_link = garnet_link->m_network_links[LinkDirection_In];
    net_link->setType(EXT_IN_);
    CreditLink* credit_link = garnet_link->m_credit_links[LinkDirection_In];

    m_networklinks.push_back(net_link);
    m_creditlinks.push_back(credit_link);

    PortDirection dst_inport_dirn = "Local";

    m_max_vcs_per_vnet = std::max(m_max_vcs_per_vnet,
                             m_routers[dest]->get_vc_per_vnet());
    m_max_link_vcs_per_vnet = std::max(m_max_link_vcs_per_vnet,
                             m_routers[dest]->get_vc_per_vnet());

    /*
     * We check if a bridge was enabled at any end of the link.
     * The bridge is enabled if either of clock domain
     * crossing (CDC) or Serializer-Deserializer(SerDes) unit is
     * enabled for the link at each end. The bridge encapsulates
     * the functionality for both CDC and SerDes and is a Consumer
     * object similiar to a NetworkLink.
     *
     * If a bridge was enabled we connect the NI and Routers to
     * bridge before connecting the link. Example, if an external
     * bridge is enabled, we would connect:
     * NI--->NetworkBridge--->GarnetExtLink---->Router
     */
    if (garnet_link->extBridgeEn) {
        DPRINTF(RubyNetwork, "Enable external bridge for %s\n",
            garnet_link->name());
        NetworkBridge *n_bridge = garnet_link->extNetBridge[LinkDirection_In];
        m_nis[local_src]->
        addOutPort(n_bridge,
                   garnet_link->extCredBridge[LinkDirection_In],
                   dest, m_routers[dest]->get_vc_per_vnet());
        m_networkbridges.push_back(n_bridge);
    } else {
        m_nis[local_src]->addOutPort(net_link, credit_link, dest,
            m_routers[dest]->get_vc_per_vnet());
    }

    if (garnet_link->intBridgeEn) {
        DPRINTF(RubyNetwork, "Enable internal bridge for %s\n",
            garnet_link->name());
        NetworkBridge *n_bridge = garnet_link->intNetBridge[LinkDirection_In];
        m_routers[dest]->
            addInPort(dst_inport_dirn,
                      n_bridge,
                      garnet_link->intCredBridge[LinkDirection_In]);
        m_networkbridges.push_back(n_bridge);
    } else {
        m_routers[dest]->addInPort(dst_inport_dirn, net_link, credit_link);
    }

}

/*
 * This function creates a link from the Network to a NI.
 * It creates a Network Link from a Router to the NI and
 * a Credit Link from NI to the Router
*/

void
GarnetNetwork::makeExtOutLink(SwitchID src, NodeID global_dest,
                              BasicLink* link,
                              std::vector<NetDest>& routing_table_entry)
{
    NodeID local_dest = getLocalNodeID(global_dest);
    assert(local_dest < m_nodes);
    assert(src < m_routers.size());
    assert(m_routers[src] != NULL);

    GarnetExtLink* garnet_link = safe_cast<GarnetExtLink*>(link);

    // GarnetExtLink is bi-directional
    NetworkLink* net_link = garnet_link->m_network_links[LinkDirection_Out];
    net_link->setType(EXT_OUT_);
    CreditLink* credit_link = garnet_link->m_credit_links[LinkDirection_Out];

    m_networklinks.push_back(net_link);
    m_creditlinks.push_back(credit_link);

    PortDirection src_outport_dirn = "Local";

    m_max_vcs_per_vnet = std::max(m_max_vcs_per_vnet,
                             m_routers[src]->get_vc_per_vnet());
    m_max_link_vcs_per_vnet = std::max(m_max_link_vcs_per_vnet,
                             m_routers[src]->get_vc_per_vnet());

    /*
     * We check if a bridge was enabled at any end of the link.
     * The bridge is enabled if either of clock domain
     * crossing (CDC) or Serializer-Deserializer(SerDes) unit is
     * enabled for the link at each end. The bridge encapsulates
     * the functionality for both CDC and SerDes and is a Consumer
     * object similiar to a NetworkLink.
     *
     * If a bridge was enabled we connect the NI and Routers to
     * bridge before connecting the link. Example, if an external
     * bridge is enabled, we would connect:
     * NI<---NetworkBridge<---GarnetExtLink<----Router
     */
    if (garnet_link->extBridgeEn) {
        DPRINTF(RubyNetwork, "Enable external bridge for %s\n",
            garnet_link->name());
        NetworkBridge *n_bridge = garnet_link->extNetBridge[LinkDirection_Out];
        m_nis[local_dest]->
            addInPort(n_bridge, garnet_link->extCredBridge[LinkDirection_Out]);
        m_networkbridges.push_back(n_bridge);
    } else {
        m_nis[local_dest]->addInPort(net_link, credit_link);
    }

    if (garnet_link->intBridgeEn) {
        DPRINTF(RubyNetwork, "Enable internal bridge for %s\n",
            garnet_link->name());
        NetworkBridge *n_bridge = garnet_link->intNetBridge[LinkDirection_Out];
        m_routers[src]->
            addOutPort(src_outport_dirn,
                       n_bridge,
                       routing_table_entry, link->m_weight,
                       garnet_link->intCredBridge[LinkDirection_Out],
                       m_routers[src]->get_vc_per_vnet());
        m_networkbridges.push_back(n_bridge);
    } else {
        m_routers[src]->
            addOutPort(src_outport_dirn, net_link,
                       routing_table_entry,
                       link->m_weight, credit_link,
                       m_routers[src]->get_vc_per_vnet());
    }
}

/*
 * This function creates an internal network link between two routers.
 * It adds both the network link and an opposite credit link.
*/

void
GarnetNetwork::makeInternalLink(SwitchID src, SwitchID dest, BasicLink* link,
                                std::vector<NetDest>& routing_table_entry,
                                PortDirection src_outport_dirn,
                                PortDirection dst_inport_dirn)
{
    GarnetIntLink* garnet_link = safe_cast<GarnetIntLink*>(link);

    // GarnetIntLink is unidirectional
    NetworkLink* net_link = garnet_link->m_network_link;
    net_link->setType(INT_);
    CreditLink* credit_link = garnet_link->m_credit_link;

    m_networklinks.push_back(net_link);
    m_creditlinks.push_back(credit_link);

    m_max_vcs_per_vnet = std::max(m_max_vcs_per_vnet,
                             std::max(m_routers[dest]->get_vc_per_vnet(),
                             m_routers[src]->get_vc_per_vnet()));
    const uint32_t consumer_vcs = m_enable_dpphys ?
        getDPPhysLogicalVCs() : m_routers[dest]->get_vc_per_vnet();
    m_max_link_vcs_per_vnet = std::max(
        m_max_link_vcs_per_vnet, consumer_vcs);

    /*
     * We check if a bridge was enabled at any end of the link.
     * The bridge is enabled if either of clock domain
     * crossing (CDC) or Serializer-Deserializer(SerDes) unit is
     * enabled for the link at each end. The bridge encapsulates
     * the functionality for both CDC and SerDes and is a Consumer
     * object similiar to a NetworkLink.
     *
     * If a bridge was enabled we connect the NI and Routers to
     * bridge before connecting the link. Example, if a source
     * bridge is enabled, we would connect:
     * Router--->NetworkBridge--->GarnetIntLink---->Router
     */
    if (garnet_link->dstBridgeEn) {
        DPRINTF(RubyNetwork, "Enable destination bridge for %s\n",
            garnet_link->name());
        NetworkBridge *n_bridge = garnet_link->dstNetBridge;
        m_routers[dest]->addInPort(dst_inport_dirn, n_bridge,
                                   garnet_link->dstCredBridge);
        m_networkbridges.push_back(n_bridge);
    } else {
        m_routers[dest]->addInPort(dst_inport_dirn, net_link, credit_link);
    }

    if (garnet_link->srcBridgeEn) {
        DPRINTF(RubyNetwork, "Enable source bridge for %s\n",
            garnet_link->name());
        NetworkBridge *n_bridge = garnet_link->srcNetBridge;
        m_routers[src]->
            addOutPort(src_outport_dirn, n_bridge,
                       routing_table_entry,
                       link->m_weight, garnet_link->srcCredBridge,
                       consumer_vcs);
        m_networkbridges.push_back(n_bridge);
    } else {
        m_routers[src]->addOutPort(src_outport_dirn, net_link,
                        routing_table_entry,
                        link->m_weight, credit_link,
                        consumer_vcs);
    }
}

// Total routers in the network
int
GarnetNetwork::getNumRouters()
{
    return m_routers.size();
}

// Get ID of router connected to a NI.
int
GarnetNetwork::get_router_id(int global_ni, int vnet)
{
    NodeID local_ni = getLocalNodeID(global_ni);

    return m_nis[local_ni]->get_router_id(vnet);
}

void
GarnetNetwork::regStats()
{
    Network::regStats();

    const auto *count = statistics::units::Count::get();
    const auto *tick = statistics::units::Tick::get();
    const auto *tick_per_count = statistics::units::Rate<
        statistics::units::Tick, statistics::units::Count>::get();
    const auto *count_per_count = statistics::units::Rate<
        statistics::units::Count, statistics::units::Count>::get();
    const auto *ratio = statistics::units::Ratio::get();

    // Packets
    m_packets_received
        .init(m_virtual_networks)
        .name(name() + ".packets_received")
        .unit(count)
        .flags(statistics::pdf | statistics::total | statistics::nozero |
            statistics::oneline)
        ;

    m_packets_injected
        .init(m_virtual_networks)
        .name(name() + ".packets_injected")
        .unit(count)
        .flags(statistics::pdf | statistics::total | statistics::nozero |
            statistics::oneline)
        ;

    m_packet_network_latency
        .init(m_virtual_networks)
        .name(name() + ".packet_network_latency")
        .unit(tick)
        .flags(statistics::oneline)
        ;

    m_packet_queueing_latency
        .init(m_virtual_networks)
        .name(name() + ".packet_queueing_latency")
        .unit(tick)
        .flags(statistics::oneline)
        ;

    for (int i = 0; i < m_virtual_networks; i++) {
        m_packets_received.subname(i, csprintf("vnet-%i", i));
        m_packets_injected.subname(i, csprintf("vnet-%i", i));
        m_packet_network_latency.subname(i, csprintf("vnet-%i", i));
        m_packet_queueing_latency.subname(i, csprintf("vnet-%i", i));
    }

    m_avg_packet_vnet_latency
        .name(name() + ".average_packet_vnet_latency")
        .unit(tick_per_count)
        .flags(statistics::oneline);
    m_avg_packet_vnet_latency =
        m_packet_network_latency / m_packets_received;

    m_avg_packet_vqueue_latency
        .name(name() + ".average_packet_vqueue_latency")
        .unit(tick_per_count)
        .flags(statistics::oneline);
    m_avg_packet_vqueue_latency =
        m_packet_queueing_latency / m_packets_received;

    m_avg_packet_network_latency
        .name(name() + ".average_packet_network_latency")
        .unit(tick_per_count);
    m_avg_packet_network_latency =
        sum(m_packet_network_latency) / sum(m_packets_received);

    m_avg_packet_queueing_latency
        .name(name() + ".average_packet_queueing_latency")
        .unit(tick_per_count);
    m_avg_packet_queueing_latency
        = sum(m_packet_queueing_latency) / sum(m_packets_received);

    m_avg_packet_latency
        .name(name() + ".average_packet_latency")
        .unit(tick_per_count);
    m_avg_packet_latency
        = m_avg_packet_network_latency + m_avg_packet_queueing_latency;

    // Flits
    m_flits_received
        .init(m_virtual_networks)
        .name(name() + ".flits_received")
        .unit(count)
        .flags(statistics::pdf | statistics::total | statistics::nozero |
            statistics::oneline)
        ;

    m_flits_injected
        .init(m_virtual_networks)
        .name(name() + ".flits_injected")
        .unit(count)
        .flags(statistics::pdf | statistics::total | statistics::nozero |
            statistics::oneline)
        ;

    m_flit_network_latency
        .init(m_virtual_networks)
        .name(name() + ".flit_network_latency")
        .unit(tick)
        .flags(statistics::oneline)
        ;

    m_flit_queueing_latency
        .init(m_virtual_networks)
        .name(name() + ".flit_queueing_latency")
        .unit(tick)
        .flags(statistics::oneline)
        ;

    for (int i = 0; i < m_virtual_networks; i++) {
        m_flits_received.subname(i, csprintf("vnet-%i", i));
        m_flits_injected.subname(i, csprintf("vnet-%i", i));
        m_flit_network_latency.subname(i, csprintf("vnet-%i", i));
        m_flit_queueing_latency.subname(i, csprintf("vnet-%i", i));
    }

    m_avg_flit_vnet_latency
        .name(name() + ".average_flit_vnet_latency")
        .unit(tick_per_count)
        .flags(statistics::oneline);
    m_avg_flit_vnet_latency = m_flit_network_latency / m_flits_received;

    m_avg_flit_vqueue_latency
        .name(name() + ".average_flit_vqueue_latency")
        .unit(tick_per_count)
        .flags(statistics::oneline);
    m_avg_flit_vqueue_latency =
        m_flit_queueing_latency / m_flits_received;

    m_avg_flit_network_latency
        .name(name() + ".average_flit_network_latency")
        .unit(tick_per_count);
    m_avg_flit_network_latency =
        sum(m_flit_network_latency) / sum(m_flits_received);

    m_avg_flit_queueing_latency
        .name(name() + ".average_flit_queueing_latency")
        .unit(tick_per_count);
    m_avg_flit_queueing_latency =
        sum(m_flit_queueing_latency) / sum(m_flits_received);

    m_avg_flit_latency
        .name(name() + ".average_flit_latency")
        .unit(tick_per_count);
    m_avg_flit_latency =
        m_avg_flit_network_latency + m_avg_flit_queueing_latency;


    // Hops
    m_total_hops.unit(count);
    m_avg_hops
        .name(name() + ".average_hops")
        .unit(count_per_count);
    m_avg_hops = m_total_hops / sum(m_flits_received);

    m_adaptive_hops
        .name(name() + ".adaptive_hops")
        .unit(count);
    m_escape_hops
        .name(name() + ".escape_hops")
        .unit(count);
    m_escape_transitions
        .name(name() + ".escape_transitions")
        .unit(count);
    m_cbs_entry_blocks
        .name(name() + ".cbs_entry_blocks")
        .unit(count);
    m_cbs_mark_moves
        .name(name() + ".cbs_mark_moves")
        .unit(count);
    m_dp_pool_blocks
        .name(name() + ".dp_pool_blocks")
        .unit(count);
    m_dp_shared_grants
        .name(name() + ".dp_shared_grants")
        .unit(count);
    m_dpphys_pool_allocations
        .name(name() + ".dpphys_pool_allocations")
        .unit(count);
    m_dpphys_owned_pool_allocations
        .name(name() + ".dpphys_owned_pool_allocations")
        .unit(count);
    m_dpphys_demand_reclaims
        .name(name() + ".dpphys_demand_reclaims")
        .unit(count);
    m_dpphys_owner_migrations
        .name(name() + ".dpphys_owner_migrations")
        .unit(count);
    m_dpphys_release_handoffs
        .name(name() + ".dpphys_release_handoffs")
        .unit(count);
    m_dpphys_release_keeps
        .name(name() + ".dpphys_release_keeps")
        .unit(count);
    m_dpphys_ownership_wait_starts
        .name(name() + ".dpphys_ownership_wait_starts")
        .unit(count);
    m_dpphys_ownership_wait_completions
        .name(name() + ".dpphys_ownership_wait_completions")
        .unit(count);
    m_dpphys_ownership_wait_cycles
        .name(name() + ".dpphys_ownership_wait_cycles")
        .unit(count);
    m_dpphys_ownership_wait_max
        .name(name() + ".dpphys_ownership_wait_max")
        .unit(count);
    m_dpphys_pool_write_blocks
        .name(name() + ".dpphys_pool_write_blocks")
        .unit(count);
    m_dpphys_pool_read_conflicts
        .name(name() + ".dpphys_pool_read_conflicts")
        .unit(count);
    m_dpphys_pool_reads
        .name(name() + ".dpphys_pool_reads")
        .unit(count);
    m_dpphys_reserved_reads
        .name(name() + ".dpphys_reserved_reads")
        .unit(count);
    m_dpphys_borrowed_peak
        .name(name() + ".dpphys_borrowed_peak")
        .unit(count);

    static const char *dpphys_directions[6] = {
        "East", "West", "North", "South", "Up", "Down"
    };
    m_dpphys_pool_allocations_by_dir
        .init(6)
        .name(name() + ".dpphys_pool_allocations_by_dir")
        .unit(count)
        .flags(statistics::total);
    m_dpphys_pool_reads_by_dir
        .init(6)
        .name(name() + ".dpphys_pool_reads_by_dir")
        .unit(count)
        .flags(statistics::total);
    m_dpphys_reserved_reads_by_dir
        .init(6)
        .name(name() + ".dpphys_reserved_reads_by_dir")
        .unit(count)
        .flags(statistics::total);
    m_dpphys_migrations_to_dir
        .init(6)
        .name(name() + ".dpphys_migrations_to_dir")
        .unit(count)
        .flags(statistics::total);
    for (int direction = 0; direction < 6; ++direction) {
        m_dpphys_pool_allocations_by_dir.subname(
            direction, dpphys_directions[direction]);
        m_dpphys_pool_reads_by_dir.subname(
            direction, dpphys_directions[direction]);
        m_dpphys_reserved_reads_by_dir.subname(
            direction, dpphys_directions[direction]);
        m_dpphys_migrations_to_dir.subname(
            direction, dpphys_directions[direction]);
    }

    // Links
    m_total_ext_in_link_utilization
        .name(name() + ".ext_in_link_utilization")
        .unit(count);
    m_total_ext_out_link_utilization
        .name(name() + ".ext_out_link_utilization")
        .unit(count);
    m_total_int_link_utilization
        .name(name() + ".int_link_utilization")
        .unit(count);
    m_average_link_utilization
        .name(name() + ".avg_link_utilization")
        .unit(ratio);
    m_average_vc_load
        .init(m_virtual_networks * m_max_link_vcs_per_vnet)
        .name(name() + ".avg_vc_load")
        .unit(ratio)
        .flags(statistics::pdf | statistics::total | statistics::nozero |
            statistics::oneline)
        ;

    // Traffic distribution
    for (int source = 0; source < m_routers.size(); ++source) {
        m_data_traffic_distribution.push_back(
            std::vector<statistics::Scalar *>());
        m_ctrl_traffic_distribution.push_back(
            std::vector<statistics::Scalar *>());

        for (int dest = 0; dest < m_routers.size(); ++dest) {
            statistics::Scalar *data_packets = new statistics::Scalar();
            statistics::Scalar *ctrl_packets = new statistics::Scalar();

            data_packets->unit(count);
            data_packets->name(name() + ".data_traffic_distribution." + "n" +
                    std::to_string(source) + "." + "n" + std::to_string(dest));
            m_data_traffic_distribution[source].push_back(data_packets);

            ctrl_packets->unit(count);
            ctrl_packets->name(name() + ".ctrl_traffic_distribution." + "n" +
                    std::to_string(source) + "." + "n" + std::to_string(dest));
            m_ctrl_traffic_distribution[source].push_back(ctrl_packets);
        }
    }
}

void
GarnetNetwork::collateStats()
{
    RubySystem *rs = params().ruby_system;
    double time_delta = double(curCycle() - rs->getStartCycle());

    for (int i = 0; i < m_networklinks.size(); i++) {
        link_type type = m_networklinks[i]->getType();
        int activity = m_networklinks[i]->getLinkUtilization();

        if (type == EXT_IN_)
            m_total_ext_in_link_utilization += activity;
        else if (type == EXT_OUT_)
            m_total_ext_out_link_utilization += activity;
        else if (type == INT_)
            m_total_int_link_utilization += activity;

        m_average_link_utilization +=
            (double(activity) / time_delta);

        std::vector<unsigned int> vc_load = m_networklinks[i]->getVcLoad();
        for (int j = 0; j < vc_load.size(); j++) {
            m_average_vc_load[j] += ((double)vc_load[j] / time_delta);
        }
    }

    // Ask the routers to collate their statistics
    for (int i = 0; i < m_routers.size(); i++) {
        m_routers[i]->collateStats();
    }
}

void
GarnetNetwork::resetStats()
{
    for (int i = 0; i < m_routers.size(); i++) {
        m_routers[i]->resetStats();
    }
    for (int i = 0; i < m_networklinks.size(); i++) {
        m_networklinks[i]->resetStats();
    }
    for (int i = 0; i < m_creditlinks.size(); i++) {
        m_creditlinks[i]->resetStats();
    }
}

void
GarnetNetwork::print(std::ostream& out) const
{
    out << "[GarnetNetwork]";
}

void
GarnetNetwork::update_traffic_distribution(RouteInfo route)
{
    int src_node = route.src_router;
    int dest_node = route.dest_router;
    int vnet = route.vnet;

    if (m_vnet_type[vnet] == DATA_VNET_)
        (*m_data_traffic_distribution[src_node][dest_node])++;
    else
        (*m_ctrl_traffic_distribution[src_node][dest_node])++;
}

bool
GarnetNetwork::functionalRead(Packet *pkt, WriteMask &mask)
{
    bool read = false;
    for (unsigned int i = 0; i < m_routers.size(); i++) {
        if (m_routers[i]->functionalRead(pkt, mask))
            read = true;
    }

    for (unsigned int i = 0; i < m_nis.size(); ++i) {
        if (m_nis[i]->functionalRead(pkt, mask))
            read = true;
    }

    for (unsigned int i = 0; i < m_networklinks.size(); ++i) {
        if (m_networklinks[i]->functionalRead(pkt, mask))
            read = true;
    }

    for (unsigned int i = 0; i < m_networkbridges.size(); ++i) {
        if (m_networkbridges[i]->functionalRead(pkt, mask))
            read = true;
    }

    return read;
}

uint32_t
GarnetNetwork::functionalWrite(Packet *pkt)
{
    uint32_t num_functional_writes = 0;

    for (unsigned int i = 0; i < m_routers.size(); i++) {
        num_functional_writes += m_routers[i]->functionalWrite(pkt);
    }

    for (unsigned int i = 0; i < m_nis.size(); ++i) {
        num_functional_writes += m_nis[i]->functionalWrite(pkt);
    }

    for (unsigned int i = 0; i < m_networklinks.size(); ++i) {
        num_functional_writes += m_networklinks[i]->functionalWrite(pkt);
    }

    return num_functional_writes;
}

} // namespace garnet
} // namespace ruby
} // namespace gem5
