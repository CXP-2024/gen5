#!/usr/bin/env python3
"""Generate explanatory diagrams for the Lab 4 report."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon


TASK_DIR = Path(__file__).resolve().parent
ADAPTIVE = "#cfe8f7"
ESCAPE = "#d8f0dc"
DECISION = "#fce7bd"
INK = "#24313d"
RED = "#c63d3d"
CHINESE_FONT = FontProperties(
    fname="/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"
)


def add_box(axis, x, y, width, height, label, color, edge=INK, fontsize=9):
    box = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.02,rounding_size=0.025",
        facecolor=color,
        edgecolor=edge,
        linewidth=1.4,
    )
    axis.add_patch(box)
    axis.text(
        x + width / 2,
        y + height / 2,
        label,
        ha="center",
        va="center",
        fontsize=fontsize,
        color=INK,
        linespacing=1.25,
    )


def arrow(axis, start, end, label=None, color=INK, style="-", offset=(0, 0)):
    patch = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=13,
        linewidth=1.5,
        linestyle=style,
        color=color,
        connectionstyle="arc3,rad=0.0",
    )
    axis.add_patch(patch)
    if label:
        axis.text(
            (start[0] + end[0]) / 2 + offset[0],
            (start[1] + end[1]) / 2 + offset[1],
            label,
            ha="center",
            va="center",
            fontsize=8,
            color=color,
        )


def save(figure, name):
    for extension in ("pdf", "png"):
        figure.savefig(
            TASK_DIR / f"{name}.{extension}",
            dpi=220,
            bbox_inches="tight",
            facecolor="white",
        )
    plt.close(figure)


def draw_architecture():
    figure, axis = plt.subplots(figsize=(10.8, 4.2))
    axis.set_xlim(0, 10.8)
    axis.set_ylim(0, 4.2)
    axis.axis("off")

    add_box(
        axis,
        0.25,
        1.7,
        1.65,
        0.72,
        "NI injection\nAdaptive VCs A0-A2",
        ADAPTIVE,
    )
    add_box(
        axis,
        2.35,
        1.48,
        2.05,
        1.16,
        "Adaptive state\nrank minimal Torus ports\nby free adaptive VCs",
        ADAPTIVE,
    )
    diamond = Polygon(
        [(5.05, 2.06), (5.72, 2.62), (6.39, 2.06), (5.72, 1.50)],
        closed=True,
        facecolor=DECISION,
        edgecolor=INK,
        linewidth=1.4,
    )
    axis.add_patch(diamond)
    axis.text(
        5.72,
        2.06,
        "Adaptive\nVC free?",
        ha="center",
        va="center",
        fontsize=8.5,
        color=INK,
    )
    add_box(
        axis,
        7.1,
        2.82,
        2.5,
        0.72,
        "Adaptive hop A -> A\nminimal Torus link; repeat",
        ADAPTIVE,
    )
    add_box(
        axis,
        7.1,
        0.56,
        2.5,
        0.9,
        "Escape state A -> E\nnon-wrap X -> Y -> Z\nthen E -> E only",
        ESCAPE,
        edge="#367a44",
    )
    add_box(
        axis, 9.92, 0.65, 0.62, 0.72, "Local\negress", ESCAPE, edge="#367a44"
    )

    arrow(axis, (1.9, 2.06), (2.35, 2.06))
    arrow(axis, (4.4, 2.06), (5.02, 2.06))
    arrow(axis, (6.33, 2.34), (7.1, 3.13), "yes", offset=(0.02, 0.18))
    arrow(axis, (6.33, 1.79), (7.1, 1.08), "no", offset=(0.02, -0.17))
    arrow(axis, (9.6, 1.01), (9.92, 1.01), color="#367a44")
    add_box(
        axis,
        1.45,
        0.16,
        5.2,
        0.72,
        "Invariant: E -> A is prohibited.\nEscape traffic never returns to adaptive VCs.",
        "#fff4f4",
        edge=RED,
        fontsize=8.5,
    )
    axis.text(
        0.25,
        3.9,
        "VC-class routing state machine",
        fontsize=12,
        weight="bold",
        color=INK,
    )
    axis.text(
        0.25,
        3.58,
        "Blue: minimal congestion-aware path. Green: connected progress path.",
        fontsize=9,
        color="#4a5a66",
    )
    save(figure, "routing_architecture")


def draw_cdg():
    figure, axis = plt.subplots(figsize=(9.6, 3.2))
    axis.set_xlim(0, 9.6)
    axis.set_ylim(0, 3.2)
    axis.axis("off")
    for x, title, detail in (
        (
            0.45,
            "Escape X channels",
            "fixed sign; monotone\ncoordinate progress",
        ),
        (
            3.55,
            "Escape Y channels",
            "fixed sign; monotone\ncoordinate progress",
        ),
        (
            6.65,
            "Escape Z channels",
            "fixed sign; monotone\ncoordinate progress",
        ),
    ):
        add_box(
            axis,
            x,
            1.28,
            2.25,
            0.96,
            f"{title}\n{detail}",
            ESCAPE,
            edge="#367a44",
        )
    arrow(axis, (2.7, 1.76), (3.55, 1.76), color="#367a44")
    arrow(axis, (5.8, 1.76), (6.65, 1.76), color="#367a44")
    axis.text(
        3.125,
        1.04,
        "only X -> Y",
        ha="center",
        va="center",
        fontsize=8,
        color="#367a44",
    )
    axis.text(
        6.225,
        1.04,
        "only Y -> Z",
        ha="center",
        va="center",
        fontsize=8,
        color="#367a44",
    )
    add_box(
        axis,
        1.1,
        0.28,
        7.35,
        0.55,
        "No legal edge returns to an earlier rank: no wrap, coordinate reversal, Z -> Y, or Y -> X.",
        "#fff4f4",
        edge=RED,
    )
    axis.text(
        0.45,
        2.86,
        "Escape-channel dependency graph: a strict ordering",
        fontsize=12,
        weight="bold",
        color=INK,
    )
    axis.text(
        0.45,
        2.57,
        "Every legal dependency advances dimension or monotone coordinate rank.",
        fontsize=9,
        color="#4a5a66",
    )
    save(figure, "escape_cdg")


def draw_cbs_bubble():
    figure, axis = plt.subplots(figsize=(10.8, 3.65))
    axis.set_xlim(0, 10.8)
    axis.set_ylim(0, 3.65)
    axis.axis("off")

    axis.text(
        0.3,
        3.3,
        "Critical Bubble Scheme: preserve one movable empty slot",
        fontsize=12,
        weight="bold",
        color=INK,
    )
    axis.text(
        0.3,
        3.02,
        "A marked free VC is protected at ring entry and relocates after in-ring transit.",
        fontsize=9,
        color="#4a5a66",
    )

    add_box(axis, 0.3, 0.72, 4.72, 1.9, "", "#f8fbfd", edge="#7a8a96")
    axis.text(
        0.56,
        2.32,
        "1. External entry at the marked port",
        fontsize=10,
        weight="bold",
        color=INK,
    )
    axis.text(
        0.56,
        2.05,
        "One free VC remains: block the new packet.",
        fontsize=8.5,
        color="#4a5a66",
    )
    add_box(
        axis,
        0.65,
        1.08,
        1.3,
        0.55,
        "incoming\npacket",
        "#fde0df",
        edge=RED,
        fontsize=8,
    )
    axis.text(
        2.15, 1.34, "blocked", fontsize=8, color=RED, ha="center", va="center"
    )
    arrow(axis, (1.95, 1.35), (2.5, 1.35), color=RED, style="--")
    axis.text(
        3.63,
        1.67,
        "downstream input",
        fontsize=8,
        color="#4a5a66",
        ha="center",
    )
    for x, color, label, edge in (
        (2.62, "#cfe8f7", "busy", INK),
        (3.17, "#cfe8f7", "busy", INK),
        (3.72, "#cfe8f7", "busy", INK),
        (4.27, "#fff1c9", "free\nmark", RED),
    ):
        add_box(axis, x, 1.06, 0.46, 0.52, label, color, edge=edge, fontsize=7)
    axis.text(
        2.66,
        0.84,
        "Entry needs >= 2 free VCs.\nThe marked bubble survives.",
        fontsize=7.1,
        color=RED,
        ha="center",
        va="center",
    )

    add_box(axis, 5.48, 0.72, 5.02, 1.9, "", "#f8fbfd", edge="#7a8a96")
    axis.text(
        5.74,
        2.32,
        "2. In-ring transit across the marked port",
        fontsize=10,
        weight="bold",
        color=INK,
    )
    axis.text(
        5.74,
        2.05,
        "A packet advances; its vacated upstream slot becomes the new mark.",
        fontsize=8.5,
        color="#4a5a66",
    )
    axis.text(6.2, 1.72, "upstream", fontsize=8, color="#4a5a66", ha="center")
    add_box(axis, 5.72, 1.08, 0.72, 0.52, "busy", ADAPTIVE, fontsize=7)
    arrow(axis, (6.51, 1.34), (7.48, 1.34), color="#367a44")
    axis.text(7.0, 1.58, "transit", fontsize=8, color="#367a44", ha="center")
    axis.text(
        8.88, 1.72, "downstream", fontsize=8, color="#4a5a66", ha="center"
    )
    add_box(axis, 8.0, 1.08, 0.72, 0.52, "busy", ADAPTIVE, fontsize=7)
    add_box(
        axis,
        8.77,
        1.08,
        0.72,
        0.52,
        "free\nmark",
        "#fff1c9",
        edge=RED,
        fontsize=7,
    )
    arrow(axis, (9.13, 0.98), (6.08, 0.98), color=RED, style="--")
    axis.text(
        7.0,
        0.84,
        "mark moves upstream",
        fontsize=7.1,
        color=RED,
        ha="center",
        va="center",
    )
    axis.text(
        9.0,
        0.84,
        "Free slots conserved;\nonly mark moves.",
        fontsize=6.9,
        color="#367a44",
        ha="center",
        va="center",
    )
    save(figure, "cbs_bubble")


def draw_member_names():
    figure, axis = plt.subplots(figsize=(5.8, 0.38))
    axis.axis("off")
    axis.text(
        0.12,
        0.5,
        "潘长浔",
        ha="center",
        va="center",
        fontsize=11,
        color=INK,
        fontproperties=CHINESE_FONT,
    )
    axis.text(
        0.35,
        0.5,
        "2024011323",
        ha="center",
        va="center",
        fontsize=9,
        color=INK,
    )
    axis.text(
        0.64,
        0.5,
        "王立明",
        ha="center",
        va="center",
        fontsize=11,
        color=INK,
        fontproperties=CHINESE_FONT,
    )
    axis.text(
        0.87,
        0.5,
        "2024011338",
        ha="center",
        va="center",
        fontsize=9,
        color=INK,
    )
    save(figure, "member_names")


if __name__ == "__main__":
    draw_architecture()
    draw_cdg()
    draw_cbs_bubble()
    draw_member_names()
