/*
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


#include "mem/ruby/network/garnet/RoutingUnit.hh"

#include "base/cast.hh"
#include "base/compiler.hh"
#include "debug/RubyNetwork.hh"
#include "mem/ruby/network/garnet/InputUnit.hh"
#include "mem/ruby/network/garnet/OutputUnit.hh"
#include "mem/ruby/network/garnet/Router.hh"
#include "mem/ruby/slicc_interface/Message.hh"

namespace gem5
{

namespace ruby
{

namespace garnet
{

RoutingUnit::RoutingUnit(Router *router)
    : m_router(router), m_random(0x5eed0000U + router->get_id())
{
    m_routing_table.clear();
    m_weight_table.clear();
}

void
RoutingUnit::addRoute(std::vector<NetDest>& routing_table_entry)
{
    if (routing_table_entry.size() > m_routing_table.size()) {
        m_routing_table.resize(routing_table_entry.size());
    }
    for (int v = 0; v < routing_table_entry.size(); v++) {
        m_routing_table[v].push_back(routing_table_entry[v]);
    }
}

void
RoutingUnit::addWeight(int link_weight)
{
    m_weight_table.push_back(link_weight);
}

bool
RoutingUnit::supportsVnet(int vnet, std::vector<int> sVnets)
{
    // If all vnets are supported, return true
    if (sVnets.size() == 0) {
        return true;
    }

    // Find the vnet in the vector, return true
    if (std::find(sVnets.begin(), sVnets.end(), vnet) != sVnets.end()) {
        return true;
    }

    // Not supported vnet
    return false;
}

/*
 * This is the default routing algorithm in garnet.
 * The routing table is populated during topology creation.
 * Routes can be biased via weight assignments in the topology file.
 * Correct weight assignments are critical to provide deadlock avoidance.
 */
int
RoutingUnit::lookupRoutingTable(int vnet, NetDest msg_destination)
{
    // First find all possible output link candidates
    // For ordered vnet, just choose the first
    // (to make sure different packets don't choose different routes)
    // For unordered vnet, randomly choose any of the links
    // To have a strict ordering between links, they should be given
    // different weights in the topology file

    int output_link = -1;
    int min_weight = INFINITE_;
    std::vector<int> output_link_candidates;
    int num_candidates = 0;

    // Identify the minimum weight among the candidate output links
    for (int link = 0; link < m_routing_table[vnet].size(); link++) {
        if (msg_destination.intersectionIsNotEmpty(
            m_routing_table[vnet][link])) {

        if (m_weight_table[link] <= min_weight)
            min_weight = m_weight_table[link];
        }
    }

    // Collect all candidate output links with this minimum weight
    for (int link = 0; link < m_routing_table[vnet].size(); link++) {
        if (msg_destination.intersectionIsNotEmpty(
            m_routing_table[vnet][link])) {

            if (m_weight_table[link] == min_weight) {
                num_candidates++;
                output_link_candidates.push_back(link);
            }
        }
    }

    if (output_link_candidates.size() == 0) {
        fatal("Fatal Error:: No Route exists from this Router.");
        exit(0);
    }

    // Randomly select any candidate output link
    int candidate = 0;
    if (!(m_router->get_net_ptr())->isVNetOrdered(vnet))
        candidate = rand() % num_candidates;

    output_link = output_link_candidates.at(candidate);
    return output_link;
}


void
RoutingUnit::addInDirection(PortDirection inport_dirn, int inport_idx)
{
    m_inports_dirn2idx[inport_dirn] = inport_idx;
    m_inports_idx2dirn[inport_idx]  = inport_dirn;
}

void
RoutingUnit::addOutDirection(PortDirection outport_dirn, int outport_idx)
{
    m_outports_dirn2idx[outport_dirn] = outport_idx;
    m_outports_idx2dirn[outport_idx]  = outport_dirn;
}

// outportCompute() is called by the InputUnit
// It calls the routing table by default.
// A template for adaptive topology-specific routing algorithm
// implementations using port directions rather than a static routing
// table is provided here.

int
RoutingUnit::outportCompute(RouteInfo route, int inport,
                            PortDirection inport_dirn, int invc)
{
    int outport = -1;

    if (route.dest_router == m_router->get_id()) {

        // Multiple NIs may be connected to this router,
        // all with output port direction = "Local"
        // Get exact outport id from table
        outport = lookupRoutingTable(route.vnet, route.net_dest);
        return outport;
    }

    // Routing Algorithm set in GarnetNetwork.py
    // Can be over-ridden from command line using --routing-algorithm = 1
    RoutingAlgorithm routing_algorithm =
        (RoutingAlgorithm) m_router->get_net_ptr()->getRoutingAlgorithm();

    switch (routing_algorithm) {
        case TABLE_:  outport =
            lookupRoutingTable(route.vnet, route.net_dest); break;
        case XY_:     outport =
            outportComputeXY(route, inport, inport_dirn); break;
        // any custom algorithm
        case CUSTOM_: outport =
            outportComputeCustom(route, inport, inport_dirn); break;
        case TORUS_3D_DOR_: outport =
            outportCompute3DDOR(route, inport, inport_dirn); break;
        case TORUS_3D_ADAPTIVE_: outport =
            outportCompute3DAdaptive(route, invc, false).outport; break;
        case MESH_3D_XYZ_: outport =
            outportCompute3DXYZ(route); break;
        default: outport =
            lookupRoutingTable(route.vnet, route.net_dest); break;
    }

    assert(outport != -1);
    return outport;
}

// XY routing implemented using port directions
// Only for reference purpose in a Mesh
// By default Garnet uses the routing table
int
RoutingUnit::outportComputeXY(RouteInfo route,
                              int inport,
                              PortDirection inport_dirn)
{
    PortDirection outport_dirn = "Unknown";

    [[maybe_unused]] int num_rows = m_router->get_net_ptr()->getNumRows();
    int num_cols = m_router->get_net_ptr()->getNumCols();
    assert(num_rows > 0 && num_cols > 0);

    int my_id = m_router->get_id();
    int my_x = my_id % num_cols;
    int my_y = my_id / num_cols;

    int dest_id = route.dest_router;
    int dest_x = dest_id % num_cols;
    int dest_y = dest_id / num_cols;

    int x_hops = abs(dest_x - my_x);
    int y_hops = abs(dest_y - my_y);

    bool x_dirn = (dest_x >= my_x);
    bool y_dirn = (dest_y >= my_y);

    // already checked that in outportCompute() function
    assert(!(x_hops == 0 && y_hops == 0));

    if (x_hops > 0) {
        if (x_dirn) {
            assert(inport_dirn == "Local" || inport_dirn == "West");
            outport_dirn = "East";
        } else {
            assert(inport_dirn == "Local" || inport_dirn == "East");
            outport_dirn = "West";
        }
    } else if (y_hops > 0) {
        if (y_dirn) {
            // "Local" or "South" or "West" or "East"
            assert(inport_dirn != "North");
            outport_dirn = "North";
        } else {
            // "Local" or "North" or "West" or "East"
            assert(inport_dirn != "South");
            outport_dirn = "South";
        }
    } else {
        // x_hops == 0 and y_hops == 0
        // this is not possible
        // already checked that in outportCompute() function
        panic("x_hops == y_hops == 0");
    }

    return m_outports_dirn2idx[outport_dirn];
}

// Template for implementing custom routing algorithm
// using port directions. (Example adaptive)
int
RoutingUnit::outportComputeCustom(RouteInfo route,
                                 int inport,
                                 PortDirection inport_dirn)
{
    const int num_routers = m_router->get_net_ptr()->getNumRouters();
    const int current_id = m_router->get_id();
    const int destination_id = route.dest_router;

    assert(num_routers == 16);
    assert(destination_id >= 0 && destination_id < num_routers);
    assert(current_id != destination_id);

    const int clockwise_hops =
        (destination_id - current_id + num_routers) % num_routers;
    const int counterclockwise_hops =
        (current_id - destination_id + num_routers) % num_routers;

    PortDirection outport_dirn;
    if (clockwise_hops <= counterclockwise_hops) {
        assert(inport_dirn == "Local" ||
               inport_dirn == "CounterClockwise");
        outport_dirn = "Clockwise";
    } else {
        assert(inport_dirn == "Local" || inport_dirn == "Clockwise");
        outport_dirn = "CounterClockwise";
    }

    return m_outports_dirn2idx[outport_dirn];
}

int
RoutingUnit::outportCompute3DDOR(RouteInfo route,
                                 int inport,
                                 PortDirection inport_dirn)
{
    const int size_x = m_router->get_net_ptr()->getTorusX();
    const int size_y = m_router->get_net_ptr()->getTorusY();
    const int size_z = m_router->get_net_ptr()->getTorusZ();
    const int num_routers = m_router->get_net_ptr()->getNumRouters();
    assert(size_x * size_y * size_z == num_routers);

    const int current_id = m_router->get_id();
    const int destination_id = route.dest_router;
    const int current_x = current_id % size_x;
    const int current_y = (current_id / size_x) % size_y;
    const int current_z = current_id / (size_x * size_y);
    const int destination_x = destination_id % size_x;
    const int destination_y = (destination_id / size_x) % size_y;
    const int destination_z = destination_id / (size_x * size_y);

    PortDirection outport_dirn = "Unknown";
    auto shortestDirection = [](int current, int destination, int size,
                                PortDirection positive,
                                PortDirection negative) {
        const int positive_hops =
            (destination - current + size) % size;
        const int negative_hops =
            (current - destination + size) % size;
        return positive_hops <= negative_hops ? positive : negative;
    };

    if (current_x != destination_x) {
        outport_dirn = shortestDirection(
            current_x, destination_x, size_x, "East", "West");
    } else if (current_y != destination_y) {
        outport_dirn = shortestDirection(
            current_y, destination_y, size_y, "North", "South");
    } else if (current_z != destination_z) {
        outport_dirn = shortestDirection(
            current_z, destination_z, size_z, "Up", "Down");
    } else {
        panic("Torus3D routing called at the destination router");
    }

    return m_outports_dirn2idx[outport_dirn];
}

int
RoutingUnit::outportCompute3DXYZ(RouteInfo route)
{
    const int size_x = m_router->get_net_ptr()->getTorusX();
    const int size_y = m_router->get_net_ptr()->getTorusY();
    const int size_z = m_router->get_net_ptr()->getTorusZ();
    assert(size_x * size_y * size_z ==
           m_router->get_net_ptr()->getNumRouters());

    const int current_id = m_router->get_id();
    const int destination_id = route.dest_router;
    const int current_x = current_id % size_x;
    const int current_y = (current_id / size_x) % size_y;
    const int current_z = current_id / (size_x * size_y);
    const int destination_x = destination_id % size_x;
    const int destination_y = (destination_id / size_x) % size_y;
    const int destination_z = destination_id / (size_x * size_y);

    PortDirection outport_dirn = "Unknown";
    if (current_x != destination_x)
        outport_dirn = destination_x > current_x ? "East" : "West";
    else if (current_y != destination_y)
        outport_dirn = destination_y > current_y ? "North" : "South";
    else if (current_z != destination_z)
        outport_dirn = destination_z > current_z ? "Up" : "Down";
    else
        panic("Mesh3D routing called at the destination router");

    return m_outports_dirn2idx.at(outport_dirn);
}

AdaptiveRouteDecision
RoutingUnit::outportCompute3DAdaptive(RouteInfo route, int invc,
                                      bool require_available)
{
    const int size_x = m_router->get_net_ptr()->getTorusX();
    const int size_y = m_router->get_net_ptr()->getTorusY();
    const int size_z = m_router->get_net_ptr()->getTorusZ();
    const int vcs_per_vnet = m_router->get_vc_per_vnet();
    const int vnet = invc / vcs_per_vnet;
    const int escape_vcs = m_router->get_net_ptr()->getEscapeVCs();
    const int adaptive_vcs = vcs_per_vnet - escape_vcs;
    const bool input_escape = escape_vcs > 0 &&
        invc % vcs_per_vnet >= adaptive_vcs;

    const int current_id = m_router->get_id();
    const int destination_id = route.dest_router;
    const int current_x = current_id % size_x;
    const int current_y = (current_id / size_x) % size_y;
    const int current_z = current_id / (size_x * size_y);
    const int destination_x = destination_id % size_x;
    const int destination_y = (destination_id / size_x) % size_y;
    const int destination_z = destination_id / (size_x * size_y);

    auto outportForDirection = [this](PortDirection direction) {
        return m_outports_dirn2idx.at(direction);
    };
    auto escapeOutport = [&]() {
        if (current_x != destination_x) {
            return outportForDirection(
                destination_x > current_x ? "East" : "West");
        }
        if (current_y != destination_y) {
            return outportForDirection(
                destination_y > current_y ? "North" : "South");
        }
        if (current_z != destination_z) {
            return outportForDirection(
                destination_z > current_z ? "Up" : "Down");
        }
        return lookupRoutingTable(route.vnet, route.net_dest);
    };
    auto hasClassVC = [&](int outport, bool escape) {
        const PortDirection outdir =
            m_router->getOutputUnit(outport)->get_direction();
        if (m_router->get_net_ptr()->dpPhysGoverns(vnet, outdir)) {
            return escape ? m_router->dpPhysHasEscapeVC(outport, vnet) :
                            m_router->dpPhysAdaptiveFreeCount(
                                outport, vnet) > 0;
        }
        const int first_offset = escape ? adaptive_vcs : 0;
        const int count = escape ? escape_vcs : adaptive_vcs;
        return m_router->getOutputUnit(outport)->has_free_vc(
            vnet, first_offset, count);
    };

    if (input_escape) {
        const int outport = escapeOutport();
        if (require_available && !hasClassVC(outport, true))
            return AdaptiveRouteDecision();
        return AdaptiveRouteDecision(outport, true);
    }

    if (current_id == destination_id) {
        const int outport = escapeOutport();
        if (!require_available || hasClassVC(outport, false))
            return AdaptiveRouteDecision(outport, false);
        if (escape_vcs > 0 && hasClassVC(outport, true))
            return AdaptiveRouteDecision(outport, true);
        return AdaptiveRouteDecision();
    }

    std::vector<int> candidates;
    std::vector<PortDirection> candidate_dirns;
    auto addMinimalDirections = [&](int current, int destination, int size,
                                    PortDirection positive,
                                    PortDirection negative) {
        if (current == destination)
            return;
        const int positive_hops =
            (destination - current + size) % size;
        const int negative_hops =
            (current - destination + size) % size;
        if (positive_hops <= negative_hops) {
            candidates.push_back(outportForDirection(positive));
            candidate_dirns.push_back(positive);
        }
        if (negative_hops <= positive_hops) {
            candidates.push_back(outportForDirection(negative));
            candidate_dirns.push_back(negative);
        }
    };

    addMinimalDirections(
        current_x, destination_x, size_x, "East", "West");
    addMinimalDirections(
        current_y, destination_y, size_y, "North", "South");
    addMinimalDirections(
        current_z, destination_z, size_z, "Up", "Down");
    assert(!candidates.empty());

    int best_credits = -1;
    std::vector<int> best_outports;
    auto *net = m_router->get_net_ptr();
    for (size_t i = 0; i < candidates.size(); i++) {
        const int outport = candidates[i];
        const int credits = net->dpPhysGoverns(vnet, candidate_dirns[i]) ?
            m_router->dpPhysAdaptiveFreeCount(outport, vnet) :
            m_router->getOutputUnit(outport)->free_vc_credit_count(
                vnet, 0, adaptive_vcs);
        if (require_available && credits == 0)
            continue;
        // DP: skip outports whose downstream dimension pair is at its
        // pool cap so the packet falls through to the escape path;
        // waiting on a capped adaptive window would sidestep the escape
        // premise of Duato's protocol.
        if (require_available && net->dpGoverns(vnet) &&
            net->dpPoolFull(
                net->cbsDownstreamRouter(current_id, candidate_dirns[i]),
                GarnetNetwork::cbsOppositeDirn(candidate_dirns[i]),
                vnet))
            continue;
        if (credits > best_credits) {
            best_credits = credits;
            best_outports.clear();
        }
        if (credits == best_credits)
            best_outports.push_back(outport);
    }

    if (!best_outports.empty()) {
        const unsigned choice = m_random.random<unsigned>(
            0, best_outports.size() - 1);
        return AdaptiveRouteDecision(best_outports[choice], false);
    }

    if (escape_vcs > 0) {
        const int outport = escapeOutport();
        if (hasClassVC(outport, true))
            return AdaptiveRouteDecision(outport, true);
    }
    return AdaptiveRouteDecision();
}

} // namespace garnet
} // namespace ruby
} // namespace gem5
