#!/usr/bin/env python3
"""M2: pair-global VC numbering for DP-Phys (Variant A).

Structure only -- behavior must be preserved:
  * PRIV (dpphys off) stays bit-identical: every touched call site either
    branches on isDPPhys() or delegates to the exact pre-M2 window code.
  * New class-based OutputUnit selectors resolve the per-port VC layout
    (baseline contiguous windows vs DP-Phys pair-global ordering).
  * isEscapeVCAt(vc, local) gives port-aware escape classification
    (Local links keep the baseline layout, pinned to the per-side
    budget r + P/2; P1-(6)).
  * outportCompute3DAdaptive/route_compute_3d_adaptive gain an
    inport_dirn parameter so input class is judged in port context.
  * InputUnit::wakeup asserts the P1 per-IU invariants (arrival id owned
    by the side; active VCs <= r + P/2).
  * --dpphys-policy / --dpphys-r flags + params + init() validation.

Each replacement asserts exactly one occurrence; files are written
atomically at the end, so a failed assertion leaves everything untouched.
"""
from pathlib import Path

GARNET = Path.home() / "gem5/src/mem/ruby/network/garnet"
CONFIGS = Path.home() / "gem5/configs"

EDITS = {}

# --------------------------------------------------------------------------
# GarnetNetwork.hh: <string> include, DP-Phys API, members
# --------------------------------------------------------------------------
EDITS[GARNET / "GarnetNetwork.hh"] = [
    (
        """#include <iostream>
#include <utility>
#include <vector>
""",
        """#include <iostream>
#include <string>
#include <utility>
#include <vector>
""",
    ),
    (
        """    std::pair<int, int>
    escapeWindow() const
    {
        const int vcs = m_max_vcs_per_vnet;
        return {vcs - (int)m_escape_vcs, (int)m_escape_vcs};
    }
""",
        """    std::pair<int, int>
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
""",
    ),
    (
        """    int m_routing_algorithm;
    bool m_enable_fault_model;
""",
        """    int m_routing_algorithm;
    std::string m_dpphys_policy;
    uint32_t m_dpphys_r;
    bool m_enable_fault_model;
""",
    ),
]

# --------------------------------------------------------------------------
# GarnetNetwork.cc: ctor params, helper definitions, init() validation
# --------------------------------------------------------------------------
EDITS[GARNET / "GarnetNetwork.cc"] = [
    (
        """    m_routing_algorithm = p.routing_algorithm;
""",
        """    m_routing_algorithm = p.routing_algorithm;
    m_dpphys_policy = p.dpphys_policy;
    m_dpphys_r = p.dpphys_r;
""",
    ),
    (
        """void
GarnetNetwork::init()
{""",
        """int
GarnetNetwork::dpphysSideOfInportDirn(const PortDirection &dirn)
{
    if (dirn == "East" || dirn == "North" || dirn == "Up")
        return 0;
    if (dirn == "West" || dirn == "South" || dirn == "Down")
        return 1;
    return -1;
}

int
GarnetNetwork::dpphysSideOfOutportDirn(const PortDirection &dirn)
{
    // An outport feeds the opposite-direction inport of the downstream
    // router (East-out arrives at West-in).
    if (dirn == "West" || dirn == "South" || dirn == "Down")
        return 0;
    if (dirn == "East" || dirn == "North" || dirn == "Up")
        return 1;
    return -1;
}

// Port-aware escape classification. DP-Phys re-numbers inter-router
// links pair-globally (escape ids r-1 and 2r-1); Local links keep the
// baseline layout with the top id of the per-side budget as escape.
bool
GarnetNetwork::isEscapeVCAt(int vc, bool local_port) const
{
    if (!isDPPhys())
        return isEscapeVC(vc);
    const int offset = vc % (int)m_max_vcs_per_vnet;
    if (local_port)
        return offset == dpphysSideBudget() - 1;
    const int r = (int)m_dpphys_r;
    return offset == r - 1 || offset == 2 * r - 1;
}

// The VC ids a port may use for one class, in availability order: own
// reserve first, then the side's home pool half, ascending -- mirrors
// the baseline availability order under the static policy.
std::vector<int>
GarnetNetwork::dpphysOrderedOffsets(bool escape, int side, bool local) const
{
    assert(isDPPhys());
    const int r = (int)m_dpphys_r;
    const int half = dpphysP() / 2;
    std::vector<int> offsets;
    if (local) {
        const int budget = dpphysSideBudget();
        if (escape) {
            offsets.push_back(budget - 1);
        } else {
            for (int i = 0; i < budget - 1; i++)
                offsets.push_back(i);
        }
        return offsets;
    }
    assert(side == 0 || side == 1);
    if (escape) {
        offsets.push_back(side * r + r - 1);
        return offsets;
    }
    for (int i = 0; i < r - 1; i++)
        offsets.push_back(side * r + i);
    for (int i = 0; i < half; i++)
        offsets.push_back(2 * r + side * half + i);
    return offsets;
}

// Which pair-global ids may physically arrive at an input unit of
// `side`. Static policy: own reserve plus the side's home pool half.
// Pool-ownership migration (M3+) widens this to the full pool range
// via the cross-IU deposit path.
bool
GarnetNetwork::dpphysOffsetAllowedAt(int offset, int side) const
{
    assert(isDPPhys());
    assert(side == 0 || side == 1);
    const int r = (int)m_dpphys_r;
    const int half = dpphysP() / 2;
    if (offset >= side * r && offset < (side + 1) * r)
        return true;
    const int pool_base = 2 * r + side * half;
    return offset >= pool_base && offset < pool_base + half;
}

// VCs an NI may inject into per vnet: the adaptive class of the Local
// link (DP-Phys pins Local links to the baseline per-side budget).
int
GarnetNetwork::injectionVCs() const
{
    if (isDPPhys())
        return dpphysSideBudget() - (int)m_escape_vcs;
    return adaptiveWindow().second;
}

void
GarnetNetwork::init()
{""",
    ),
    (
        """    if (m_enable_cbs)
        cbsInit();
""",
        """    if (m_enable_cbs)
        cbsInit();

    if (isDPPhys()) {
        fatal_if(!isTorus3DAdaptive(),
            "--dpphys-policy requires Torus3D adaptive routing "
            "(--routing-algorithm=4)");
        fatal_if(m_dpphys_policy != "static",
            "unimplemented --dpphys-policy '%s' (available: static)",
            m_dpphys_policy);
        fatal_if(m_escape_vcs != 1,
            "DP-Phys requires --escape-vcs=1: each side's reserve holds "
            "exactly one escape VC");
        fatal_if(m_dpphys_r < 2,
            "DP-Phys requires --dpphys-r >= 2: a side's reserve must "
            "hold one adaptive and one escape VC");
        const int pool = (int)m_max_vcs_per_vnet - 2 * (int)m_dpphys_r;
        fatal_if(pool < 2 || pool % 2 != 0,
            "DP-Phys requires --vcs-per-vnet == 2*dpphys-r + P with an "
            "even shared pool P >= 2 (got vcs=%d, r=%d)",
            m_max_vcs_per_vnet, m_dpphys_r);
    }
""",
    ),
]

# --------------------------------------------------------------------------
# GarnetNetwork.py: new params
# --------------------------------------------------------------------------
EDITS[GARNET / "GarnetNetwork.py"] = [
    (
        """    enable_cbs = Param.Bool(
        False,
        "critical bubble scheme flow control on Torus3D rings (ctrl vnets)",
    )
""",
        """    enable_cbs = Param.Bool(
        False,
        "critical bubble scheme flow control on Torus3D rings (ctrl vnets)",
    )
    dpphys_policy = Param.String(
        "",
        "DP-Phys pooled-VC policy for adaptive torus routing; empty "
        "string disables",
    )
    dpphys_r = Param.UInt32(
        2, "DP-Phys reserved VCs per side (includes the escape VC)"
    )
""",
    ),
]

# --------------------------------------------------------------------------
# configs/network/Network.py: CLI flags + assignment
# --------------------------------------------------------------------------
EDITS[CONFIGS / "network/Network.py"] = [
    (
        """    parser.add_argument(
        "--enable-cbs",
        action="store_true",
        default=False,
        help=\"\"\"enable Critical Bubble Scheme flow control on Torus3D
            rings; requires --routing-algorithm=3 and no --wormhole\"\"\",
    )
""",
        """    parser.add_argument(
        "--enable-cbs",
        action="store_true",
        default=False,
        help=\"\"\"enable Critical Bubble Scheme flow control on Torus3D
            rings; requires --routing-algorithm=3 and no --wormhole\"\"\",
    )
    parser.add_argument(
        "--dpphys-policy",
        action="store",
        type=str,
        default="",
        help=\"\"\"DP-Phys pooled-VC policy for routing-algorithm 4;
            empty string disables (implemented: static)\"\"\",
    )
    parser.add_argument(
        "--dpphys-r",
        action="store",
        type=int,
        default=2,
        help=\"\"\"DP-Phys reserved VCs per side, escape VC included;
            the shared pool is vcs-per-vnet - 2*r\"\"\",
    )
""",
    ),
    (
        """        network.enable_cbs = options.enable_cbs
""",
        """        network.enable_cbs = options.enable_cbs
        network.dpphys_policy = options.dpphys_policy
        network.dpphys_r = options.dpphys_r
""",
    ),
]

# --------------------------------------------------------------------------
# OutputUnit.hh: class-based selector declarations
# --------------------------------------------------------------------------
EDITS[GARNET / "OutputUnit.hh"] = [
    (
        """    bool has_free_vc(int vnet, int first_offset, int count);
    int select_free_vc(int vnet, int first_offset, int count);
    int free_vc_credit_count(int vnet, int first_offset, int count);
    int count_free_vcs(int vnet);
""",
        """    bool has_free_vc(int vnet, int first_offset, int count);
    int select_free_vc(int vnet, int first_offset, int count);
    int free_vc_credit_count(int vnet, int first_offset, int count);
    int count_free_vcs(int vnet);
    bool has_free_vc_class(int vnet, bool escape);
    int select_free_vc_class(int vnet, bool escape);
    int free_vc_credit_count_class(int vnet, bool escape);
""",
    ),
    (
        """  private:
    Router *m_router;
""",
        """  private:
    std::vector<int> dpphys_offsets(bool escape);

    Router *m_router;
""",
    ),
]

# --------------------------------------------------------------------------
# OutputUnit.cc: include + class-based selector definitions
# --------------------------------------------------------------------------
EDITS[GARNET / "OutputUnit.cc"] = [
    (
        """#include "mem/ruby/network/garnet/CreditLink.hh"
#include "mem/ruby/network/garnet/Router.hh"
""",
        """#include "mem/ruby/network/garnet/CreditLink.hh"
#include "mem/ruby/network/garnet/GarnetNetwork.hh"
#include "mem/ruby/network/garnet/Router.hh"
""",
    ),
    (
        """        if (is_vc_idle(vc, curTick()))
            credits += outVcState[vc].get_credit_count();
    }

    return credits;
}
""",
        """        if (is_vc_idle(vc, curTick()))
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
        if (is_vc_idle(vc, curTick())) {
            outVcState[vc].setState(ACTIVE_, curTick());
            return vc;
        }
    }
    return -1;
}
""",
    ),
]

# --------------------------------------------------------------------------
# RoutingUnit.hh / .cc: inport_dirn parameter + class-based queries
# --------------------------------------------------------------------------
EDITS[GARNET / "RoutingUnit.hh"] = [
    (
        """    AdaptiveRouteDecision outportCompute3DAdaptive(
        RouteInfo route, int invc, bool require_available);
""",
        """    AdaptiveRouteDecision outportCompute3DAdaptive(
        RouteInfo route, int invc, bool require_available,
        PortDirection inport_dirn);
""",
    ),
]

EDITS[GARNET / "RoutingUnit.cc"] = [
    (
        """        case TORUS_3D_ADAPTIVE_: outport =
            outportCompute3DAdaptive(route, invc, false).outport; break;
""",
        """        case TORUS_3D_ADAPTIVE_: outport =
            outportCompute3DAdaptive(
                route, invc, false, inport_dirn).outport; break;
""",
    ),
    (
        """AdaptiveRouteDecision
RoutingUnit::outportCompute3DAdaptive(RouteInfo route, int invc,
                                      bool require_available)
{
""",
        """AdaptiveRouteDecision
RoutingUnit::outportCompute3DAdaptive(RouteInfo route, int invc,
                                      bool require_available,
                                      PortDirection inport_dirn)
{
""",
    ),
    (
        """    const bool input_escape = m_router->get_net_ptr()->isEscapeVC(invc);
""",
        """    const bool input_escape = m_router->get_net_ptr()->isEscapeVCAt(
        invc, inport_dirn == "Local");
""",
    ),
    (
        """    auto hasClassVC = [&](int outport, bool escape) {
        const auto window = escape ?
            m_router->get_net_ptr()->escapeWindow() :
            m_router->get_net_ptr()->adaptiveWindow();
        return m_router->getOutputUnit(outport)->has_free_vc(
            vnet, window.first, window.second);
    };
""",
        """    auto hasClassVC = [&](int outport, bool escape) {
        return m_router->getOutputUnit(outport)->has_free_vc_class(
            vnet, escape);
    };
""",
    ),
    (
        """    const auto adaptive = m_router->get_net_ptr()->adaptiveWindow();
    int best_credits = -1;
    std::vector<int> best_outports;
    for (const int outport : candidates) {
        const int credits = m_router->getOutputUnit(outport)->
            free_vc_credit_count(vnet, adaptive.first, adaptive.second);
""",
        """    int best_credits = -1;
    std::vector<int> best_outports;
    for (const int outport : candidates) {
        const int credits = m_router->getOutputUnit(outport)->
            free_vc_credit_count_class(vnet, false);
""",
    ),
]

# --------------------------------------------------------------------------
# Router.hh / .cc: thread inport_dirn through the wrapper
# --------------------------------------------------------------------------
EDITS[GARNET / "Router.hh"] = [
    (
        """    AdaptiveRouteDecision route_compute_3d_adaptive(
        RouteInfo route, int invc, bool require_available);
""",
        """    AdaptiveRouteDecision route_compute_3d_adaptive(
        RouteInfo route, int invc, bool require_available,
        PortDirection inport_dirn);
""",
    ),
]

EDITS[GARNET / "Router.cc"] = [
    (
        """AdaptiveRouteDecision
Router::route_compute_3d_adaptive(RouteInfo route, int invc,
                                  bool require_available)
{
    return routingUnit.outportCompute3DAdaptive(
        route, invc, require_available);
}
""",
        """AdaptiveRouteDecision
Router::route_compute_3d_adaptive(RouteInfo route, int invc,
                                  bool require_available,
                                  PortDirection inport_dirn)
{
    return routingUnit.outportCompute3DAdaptive(
        route, invc, require_available, inport_dirn);
}
""",
    ),
]

# --------------------------------------------------------------------------
# SwitchAllocator.cc: port-aware classification + class-based selectors
# --------------------------------------------------------------------------
EDITS[GARNET / "SwitchAllocator.cc"] = [
    (
        """                        AdaptiveRouteDecision decision =
                            m_router->route_compute_3d_adaptive(
                                input_unit->peekTopFlit(invc)->get_route(),
                                invc, true);
""",
        """                        AdaptiveRouteDecision decision =
                            m_router->route_compute_3d_adaptive(
                                input_unit->peekTopFlit(invc)->get_route(),
                                invc, true, input_unit->get_direction());
""",
    ),
    (
        """                    } else {
                        escape_request =
                            m_router->get_net_ptr()->isEscapeVC(outvc);
                    }
""",
        """                    } else {
                        const bool outport_local =
                            m_router->getOutputUnit(outport)->
                                get_direction() == "Local";
                        escape_request = m_router->get_net_ptr()->
                            isEscapeVCAt(outvc, outport_local);
                    }
""",
    ),
    (
        """                    const bool output_escape =
                        m_router->get_net_ptr()->isEscapeVC(outvc);
                    const bool input_escape =
                        m_router->get_net_ptr()->isEscapeVC(invc);
""",
        """                    const bool output_escape =
                        m_router->get_net_ptr()->isEscapeVCAt(
                            outvc, false);
                    const bool input_escape =
                        m_router->get_net_ptr()->isEscapeVCAt(invc,
                            input_unit->get_direction() == "Local");
""",
    ),
    (
        """        bool output_available = false;
        if (m_router->get_net_ptr()->isTorus3DAdaptive()) {
            const auto window = escape_request ?
                m_router->get_net_ptr()->escapeWindow() :
                m_router->get_net_ptr()->adaptiveWindow();
            output_available = output_unit->has_free_vc(
                vnet, window.first, window.second);
        } else {
""",
        """        bool output_available = false;
        if (m_router->get_net_ptr()->isTorus3DAdaptive()) {
            output_available = output_unit->has_free_vc_class(
                vnet, escape_request);
        } else {
""",
    ),
    (
        """    if (m_router->get_net_ptr()->isTorus3DAdaptive()) {
        const auto window = escape_request ?
            m_router->get_net_ptr()->escapeWindow() :
            m_router->get_net_ptr()->adaptiveWindow();
        outvc = m_router->getOutputUnit(outport)->select_free_vc(
            vnet, window.first, window.second);
""",
        """    if (m_router->get_net_ptr()->isTorus3DAdaptive()) {
        outvc = m_router->getOutputUnit(outport)->select_free_vc_class(
            vnet, escape_request);
""",
    ),
]

# --------------------------------------------------------------------------
# NetworkInterface.cc: injection VC count (Local pin)
# --------------------------------------------------------------------------
EDITS[GARNET / "NetworkInterface.cc"] = [
    (
        """    const int allocatable_vcs = m_net_ptr->isTorus3DAdaptive() ?
        m_net_ptr->adaptiveWindow().second : m_vc_per_vnet;
""",
        """    const int allocatable_vcs = m_net_ptr->isTorus3DAdaptive() ?
        m_net_ptr->injectionVCs() : m_vc_per_vnet;
""",
    ),
]

# --------------------------------------------------------------------------
# InputUnit.cc: P1 per-IU invariants
# --------------------------------------------------------------------------
EDITS[GARNET / "InputUnit.cc"] = [
    (
        """        int vc = t_flit->get_vc();
        t_flit->increment_hops(); // for stats

        int vnet = vc/m_vc_per_vnet;
""",
        """        int vc = t_flit->get_vc();
        t_flit->increment_hops(); // for stats

        auto *net = m_router->get_net_ptr();
        if (net->isDPPhys() && m_direction != "Local") {
            // DP-Phys P1: a flit may only arrive on a VC id owned by
            // this input port's side of the pair.
            assert(net->dpphysOffsetAllowedAt(
                vc % m_vc_per_vnet,
                GarnetNetwork::dpphysSideOfInportDirn(m_direction)));
        }

        int vnet = vc/m_vc_per_vnet;
""",
    ),
    (
        """        } else {
            assert(virtualChannels[vc].get_state() == ACTIVE_);
        }


        // Buffer the flit
""",
        """        } else {
            assert(virtualChannels[vc].get_state() == ACTIVE_);
        }

        if (net->isDPPhys() && m_direction != "Local" && is_head) {
            // DP-Phys P1: per-IU active VCs never exceed the per-side
            // budget r + P/2.
            int active = 0;
            const int vc_base = vnet * m_vc_per_vnet;
            for (int i = 0; i < m_vc_per_vnet; i++) {
                if (virtualChannels[vc_base + i].get_state() == ACTIVE_)
                    active++;
            }
            assert(active <= net->dpphysSideBudget());
        }

        // Buffer the flit
""",
    ),
]


def main() -> None:
    staged = {}
    for path, pairs in EDITS.items():
        text = path.read_text()
        for i, (old, new) in enumerate(pairs):
            n = text.count(old)
            assert n == 1, f"{path.name} edit {i}: expected 1 match, got {n}"
            text = text.replace(old, new)
        staged[path] = text
    for path, text in staged.items():
        path.write_text(text)
        print(f"edited {path.name}")


if __name__ == "__main__":
    main()
