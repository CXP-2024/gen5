#!/usr/bin/env python3
"""M1: replace the 8 inline escape-VC arithmetic sites with the
GarnetNetwork helpers (isEscapeVC / escapeWindow / adaptiveWindow).
Pure refactor -- every replacement is value-identical in homogeneous
configs (m_max_vcs_per_vnet == every local vc_per_vnet == p.vcs_per_vnet).

Each replacement asserts exactly one occurrence; files are written
atomically at the end, so a failed assertion leaves everything untouched.
"""
from pathlib import Path

GARNET = Path.home() / "gem5/src/mem/ruby/network/garnet"

EDITS = {
    "RoutingUnit.cc": [
        (
            """    const int escape_vcs = m_router->get_net_ptr()->getEscapeVCs();
    const int adaptive_vcs = vcs_per_vnet - escape_vcs;
    const bool input_escape = escape_vcs > 0 &&
        invc % vcs_per_vnet >= adaptive_vcs;
""",
            """    const int escape_vcs = m_router->get_net_ptr()->getEscapeVCs();
    const bool input_escape = m_router->get_net_ptr()->isEscapeVC(invc);
""",
        ),
        (
            """    auto hasClassVC = [&](int outport, bool escape) {
        const int first_offset = escape ? adaptive_vcs : 0;
        const int count = escape ? escape_vcs : adaptive_vcs;
        return m_router->getOutputUnit(outport)->has_free_vc(
            vnet, first_offset, count);
    };
""",
            """    auto hasClassVC = [&](int outport, bool escape) {
        const auto window = escape ?
            m_router->get_net_ptr()->escapeWindow() :
            m_router->get_net_ptr()->adaptiveWindow();
        return m_router->getOutputUnit(outport)->has_free_vc(
            vnet, window.first, window.second);
    };
""",
        ),
        (
            """    int best_credits = -1;
    std::vector<int> best_outports;
    for (const int outport : candidates) {
        const int credits = m_router->getOutputUnit(outport)->
            free_vc_credit_count(vnet, 0, adaptive_vcs);
""",
            """    const auto adaptive = m_router->get_net_ptr()->adaptiveWindow();
    int best_credits = -1;
    std::vector<int> best_outports;
    for (const int outport : candidates) {
        const int credits = m_router->getOutputUnit(outport)->
            free_vc_credit_count(vnet, adaptive.first, adaptive.second);
""",
        ),
    ],
    "SwitchAllocator.cc": [
        (
            """                    } else {
                        const int escape_vcs =
                            m_router->get_net_ptr()->getEscapeVCs();
                        escape_request = escape_vcs > 0 &&
                            outvc % m_vc_per_vnet >=
                            m_vc_per_vnet - escape_vcs;
                    }
""",
            """                    } else {
                        escape_request =
                            m_router->get_net_ptr()->isEscapeVC(outvc);
                    }
""",
        ),
        (
            """                    const int escape_vcs =
                        m_router->get_net_ptr()->getEscapeVCs();
                    const int adaptive_vcs = m_vc_per_vnet - escape_vcs;
                    const bool output_escape =
                        escape_vcs > 0 &&
                        outvc % m_vc_per_vnet >= adaptive_vcs;
                    const bool input_escape =
                        escape_vcs > 0 &&
                        invc % m_vc_per_vnet >= adaptive_vcs;
""",
            """                    const bool output_escape =
                        m_router->get_net_ptr()->isEscapeVC(outvc);
                    const bool input_escape =
                        m_router->get_net_ptr()->isEscapeVC(invc);
""",
        ),
        (
            """        if (m_router->get_net_ptr()->isTorus3DAdaptive()) {
            const int escape_vcs =
                m_router->get_net_ptr()->getEscapeVCs();
            const int adaptive_vcs = m_vc_per_vnet - escape_vcs;
            const int first_offset = escape_request ?
                adaptive_vcs : 0;
            const int count = escape_request ? escape_vcs : adaptive_vcs;
            output_available = output_unit->has_free_vc(
                vnet, first_offset, count);
        } else {
""",
            """        if (m_router->get_net_ptr()->isTorus3DAdaptive()) {
            const auto window = escape_request ?
                m_router->get_net_ptr()->escapeWindow() :
                m_router->get_net_ptr()->adaptiveWindow();
            output_available = output_unit->has_free_vc(
                vnet, window.first, window.second);
        } else {
""",
        ),
        (
            """    if (m_router->get_net_ptr()->isTorus3DAdaptive()) {
        const int escape_vcs = m_router->get_net_ptr()->getEscapeVCs();
        const int adaptive_vcs = m_vc_per_vnet - escape_vcs;
        const int first_offset = escape_request ? adaptive_vcs : 0;
        const int count = escape_request ? escape_vcs : adaptive_vcs;
        outvc = m_router->getOutputUnit(outport)->select_free_vc(
            vnet, first_offset, count);
""",
            """    if (m_router->get_net_ptr()->isTorus3DAdaptive()) {
        const auto window = escape_request ?
            m_router->get_net_ptr()->escapeWindow() :
            m_router->get_net_ptr()->adaptiveWindow();
        outvc = m_router->getOutputUnit(outport)->select_free_vc(
            vnet, window.first, window.second);
""",
        ),
    ],
    "NetworkInterface.cc": [
        (
            """    const int allocatable_vcs = m_net_ptr->isTorus3DAdaptive() ?
        m_vc_per_vnet - m_net_ptr->getEscapeVCs() : m_vc_per_vnet;
""",
            """    const int allocatable_vcs = m_net_ptr->isTorus3DAdaptive() ?
        m_net_ptr->adaptiveWindow().second : m_vc_per_vnet;
""",
        ),
    ],
}


def main() -> None:
    staged = {}
    for fname, pairs in EDITS.items():
        path = GARNET / fname
        text = path.read_text()
        for i, (old, new) in enumerate(pairs):
            n = text.count(old)
            assert n == 1, f"{fname} edit {i}: expected 1 match, got {n}"
            text = text.replace(old, new)
        staged[path] = text
    for path, text in staged.items():
        path.write_text(text)
        print(f"edited {path.name}")


if __name__ == "__main__":
    main()
