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


#ifndef __MEM_RUBY_NETWORK_GARNET_0_GARNETNETWORK_HH__
#define __MEM_RUBY_NETWORK_GARNET_0_GARNETNETWORK_HH__

#include <iostream>
#include <string>
#include <utility>
#include <vector>

#include "mem/ruby/network/Network.hh"
#include "mem/ruby/network/fault_model/FaultModel.hh"
#include "mem/ruby/network/garnet/CommonTypes.hh"
#include "params/GarnetNetwork.hh"

namespace gem5
{

namespace ruby
{

class FaultModel;
class NetDest;

namespace garnet
{

class NetworkInterface;
class Router;
class NetworkLink;
class NetworkBridge;
class CreditLink;

class GarnetNetwork : public Network
{
  public:
    typedef GarnetNetworkParams Params;
    GarnetNetwork(const Params &p);
    ~GarnetNetwork() = default;

    void init();

    const char *garnetVersion = "3.0";

    // Configuration (set externally)

    // for 2D topology
    int getNumRows() const { return m_num_rows; }
    int getNumCols() { return m_num_cols; }
    uint32_t getTorusX() const { return m_torus_x; }
    uint32_t getTorusY() const { return m_torus_y; }
    uint32_t getTorusZ() const { return m_torus_z; }
    uint32_t getEscapeVCs() const { return m_escape_vcs; }

    bool
    isEscapeVC(int vc) const
    {
        const int offset = vc % (int)m_max_vcs_per_vnet;
        return m_escape_vcs > 0 &&
               offset >= (int)m_max_vcs_per_vnet - (int)m_escape_vcs;
    }

    std::pair<int, int>
    adaptiveWindow() const
    {
        return {0, (int)m_max_vcs_per_vnet - (int)m_escape_vcs};
    }

    std::pair<int, int>
    escapeWindow() const
    {
        const int vcs = m_max_vcs_per_vnet;
        return {vcs - (int)m_escape_vcs, (int)m_escape_vcs};
    }

    // DP-Phys (Variant A): the opposing input ports of a dimension
    // share one pair-global VC id space of 2r + P slots per vnet.
    // Side s owns reserve ids [s*r, (s+1)*r), whose top id is its
    // escape VC, and is home to pool half [2r + s*P/2, 2r + (s+1)*P/2).
    // Local links keep the baseline layout, pinned to the per-side
    // budget r + P/2 with its top id as the escape VC, so injection
    // buffering matches the PRIV baseline.
    bool isDPPhys() const { return !m_dpphys_policy.empty(); }
    const std::string &dpphysPolicy() const { return m_dpphys_policy; }
    int dpphysR() const { return m_dpphys_r; }

    int
    dpphysP() const
    {
        return (int)m_max_vcs_per_vnet - 2 * (int)m_dpphys_r;
    }

    int
    dpphysSideBudget() const
    {
        return (int)m_dpphys_r + dpphysP() / 2;
    }

    static int dpphysSideOfInportDirn(const PortDirection &dirn);
    static int dpphysSideOfOutportDirn(const PortDirection &dirn);
    bool isEscapeVCAt(int vc, bool local_port) const;
    std::vector<int> dpphysOrderedOffsets(bool escape, int side,
                                          bool local) const;
    bool dpphysOffsetAllowedAt(int offset, int side) const;
    int injectionVCs() const;

    // for network
    uint32_t getNiFlitSize() const { return m_ni_flit_size; }
    uint32_t getBuffersPerDataVC() { return m_buffers_per_data_vc; }
    uint32_t getBuffersPerCtrlVC() { return m_buffers_per_ctrl_vc; }
    int getRoutingAlgorithm() const { return m_routing_algorithm; }
    bool isWormhole() const { return m_wormhole; }
    bool isCBSEnabled() const { return m_enable_cbs; }
    bool
    isTorus3DAdaptive() const
    {
        return m_routing_algorithm == TORUS_3D_ADAPTIVE_;
    }

    bool isFaultModelEnabled() const { return m_enable_fault_model; }
    FaultModel* fault_model;


    // Internal configuration
    bool isVNetOrdered(int vnet) const { return m_ordered[vnet]; }
    VNET_type
    get_vnet_type(int vnet)
    {
        return m_vnet_type[vnet];
    }
    int getNumRouters();
    int get_router_id(int ni, int vnet);


    // Methods used by Topology to setup the network
    void makeExtOutLink(SwitchID src, NodeID dest, BasicLink* link,
                     std::vector<NetDest>& routing_table_entry);
    void makeExtInLink(NodeID src, SwitchID dest, BasicLink* link,
                    std::vector<NetDest>& routing_table_entry);
    void makeInternalLink(SwitchID src, SwitchID dest, BasicLink* link,
                          std::vector<NetDest>& routing_table_entry,
                          PortDirection src_outport_dirn,
                          PortDirection dest_inport_dirn);

    bool functionalRead(Packet *pkt, WriteMask &mask);
    //! Function for performing a functional write. The return value
    //! indicates the number of messages that were written.
    uint32_t functionalWrite(Packet *pkt);

    // Stats
    void collateStats();
    void regStats();
    void resetStats();
    void print(std::ostream& out) const;

    // increment counters
    void increment_injected_packets(int vnet) { m_packets_injected[vnet]++; }
    void increment_received_packets(int vnet) { m_packets_received[vnet]++; }

    void
    increment_packet_network_latency(Tick latency, int vnet)
    {
        m_packet_network_latency[vnet] += latency;
    }

    void
    increment_packet_queueing_latency(Tick latency, int vnet)
    {
        m_packet_queueing_latency[vnet] += latency;
    }

    void increment_injected_flits(int vnet) { m_flits_injected[vnet]++; }
    void increment_received_flits(int vnet) { m_flits_received[vnet]++; }

    void
    increment_flit_network_latency(Tick latency, int vnet)
    {
        m_flit_network_latency[vnet] += latency;
    }

    void
    increment_flit_queueing_latency(Tick latency, int vnet)
    {
        m_flit_queueing_latency[vnet] += latency;
    }

    void
    increment_total_hops(int hops)
    {
        m_total_hops += hops;
    }

    void increment_adaptive_hop() { m_adaptive_hops++; }
    void increment_escape_hop() { m_escape_hops++; }
    void increment_escape_transition() { m_escape_transitions++; }

    // Critical Bubble Scheme (CBS): one critical bubble per directed torus
    // ring per vnet, tracked at the input port that hosts it. Hardware
    // would piggyback the mark on credits; the simulator keeps a global
    // registry indexed by (router, inport direction, vnet).
    bool cbsHasMark(int router_id, const PortDirection &inport_dirn,
                    int vnet) const;
    void cbsMoveMark(int from_router, const PortDirection &from_inport,
                     int to_router, const PortDirection &to_inport,
                     int vnet);
    int cbsDownstreamRouter(int router_id,
                            const PortDirection &outport_dirn) const;
    static PortDirection cbsOppositeDirn(const PortDirection &dirn);
    void increment_cbs_entry_block() { m_cbs_entry_blocks++; }

    void update_traffic_distribution(RouteInfo route);
    int getNextPacketID() { return m_next_packet_id++; }

  protected:
    // Configuration
    int m_num_rows;
    int m_num_cols;
    uint32_t m_torus_x;
    uint32_t m_torus_y;
    uint32_t m_torus_z;
    uint32_t m_ni_flit_size;
    uint32_t m_max_vcs_per_vnet;
    uint32_t m_escape_vcs;
    uint32_t m_buffers_per_ctrl_vc;
    bool m_wormhole;
    bool m_enable_cbs;
    uint32_t m_buffers_per_data_vc;
    int m_routing_algorithm;
    std::string m_dpphys_policy;
    uint32_t m_dpphys_r;
    bool m_enable_fault_model;

    // CBS critical bubble registry: m_cbs_mark[router][dirn][vnet] is true
    // when the input port of `router` facing direction `dirn` hosts the
    // critical bubble of its directed ring.
    std::vector<std::vector<std::vector<bool>>> m_cbs_mark;
    void cbsInit();
    static int cbsDirnIndex(const PortDirection &dirn);

    // Statistical variables
    statistics::Vector m_packets_received;
    statistics::Vector m_packets_injected;
    statistics::Vector m_packet_network_latency;
    statistics::Vector m_packet_queueing_latency;

    statistics::Formula m_avg_packet_vnet_latency;
    statistics::Formula m_avg_packet_vqueue_latency;
    statistics::Formula m_avg_packet_network_latency;
    statistics::Formula m_avg_packet_queueing_latency;
    statistics::Formula m_avg_packet_latency;

    statistics::Vector m_flits_received;
    statistics::Vector m_flits_injected;
    statistics::Vector m_flit_network_latency;
    statistics::Vector m_flit_queueing_latency;

    statistics::Formula m_avg_flit_vnet_latency;
    statistics::Formula m_avg_flit_vqueue_latency;
    statistics::Formula m_avg_flit_network_latency;
    statistics::Formula m_avg_flit_queueing_latency;
    statistics::Formula m_avg_flit_latency;

    statistics::Scalar m_total_ext_in_link_utilization;
    statistics::Scalar m_total_ext_out_link_utilization;
    statistics::Scalar m_total_int_link_utilization;
    statistics::Scalar m_average_link_utilization;
    statistics::Vector m_average_vc_load;

    statistics::Scalar  m_total_hops;
    statistics::Formula m_avg_hops;
    statistics::Scalar m_adaptive_hops;
    statistics::Scalar m_escape_hops;
    statistics::Scalar m_escape_transitions;
    statistics::Scalar m_cbs_entry_blocks;
    statistics::Scalar m_cbs_mark_moves;

    std::vector<std::vector<statistics::Scalar *>> m_data_traffic_distribution;
    std::vector<std::vector<statistics::Scalar *>> m_ctrl_traffic_distribution;

  private:
    GarnetNetwork(const GarnetNetwork& obj);
    GarnetNetwork& operator=(const GarnetNetwork& obj);

    std::vector<VNET_type > m_vnet_type;
    std::vector<Router *> m_routers;   // All Routers in Network
    std::vector<NetworkLink *> m_networklinks; // All flit links in the network
    std::vector<NetworkBridge *> m_networkbridges; // All network bridges
    std::vector<CreditLink *> m_creditlinks; // All credit links in the network
    std::vector<NetworkInterface *> m_nis;   // All NI's in Network
    int m_next_packet_id; // static vairable for packet id allocation
};

inline std::ostream&
operator<<(std::ostream& out, const GarnetNetwork& obj)
{
    obj.print(out);
    out << std::flush;
    return out;
}

} // namespace garnet
} // namespace ruby
} // namespace gem5

#endif //__MEM_RUBY_NETWORK_GARNET_0_GARNETNETWORK_HH__
