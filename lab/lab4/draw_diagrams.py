#!/usr/bin/env python3
"""Generate explanatory diagrams for the Lab 4 report."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon


TASK_DIR = Path(__file__).resolve().parent
ADAPTIVE = "#cfe8f7"
ESCAPE = "#d8f0dc"
DECISION = "#fce7bd"
INK = "#24313d"
RED = "#c63d3d"


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


if __name__ == "__main__":
    draw_architecture()
    draw_cdg()
