#!/usr/bin/env python3
"""Schematic diagrams for the DP report (matplotlib, same visual language
as ../draw_diagrams.py). Outputs: dp_concept.pdf, dp_safety.pdf,
dp_check_placement.pdf (+ .png previews)."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle

DARK = "#2c3e50"
BLUE_F, BLUE_E = "#d6e8f7", "#1f618d"
GRAY_F, GRAY_E = "#e8e8e8", "#5d6d7e"
GREEN_F, GREEN_E = "#d9f2d9", "#1e8449"
ORANGE_F, ORANGE_E = "#fce8c8", "#b9770e"
RED_E = "#c0392b"

plt.rcParams.update({"font.size": 13, "font.family": "DejaVu Sans"})


def box(ax, x, y, w, h, text, fc, ec, fs=12, lw=1.8, style="round,pad=0.06", tc=DARK, weight="normal"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=style, fc=fc, ec=ec, lw=lw))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=tc, weight=weight)


def arrow(ax, p0, p1, color=DARK, lw=2.4, style="-|>", ms=22, ls="-"):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle=style, mutation_scale=ms,
                                 color=color, lw=lw, linestyle=ls, shrinkA=2, shrinkB=2))


def save(fig, stem):
    fig.savefig(stem + ".pdf", bbox_inches="tight")
    fig.savefig(stem + ".png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    print("wrote", stem + ".pdf")


# ---------------------------------------------------------------- concept
def concept():
    fig, ax = plt.subplots(figsize=(11.2, 6.2))
    ax.set_xlim(0, 11.2); ax.set_ylim(0, 6.2); ax.axis("off")

    ax.text(0.15, 5.92, "Dimension Pool: one occupancy budget across opposing inports",
            fontsize=16, weight="bold", color=DARK)
    ax.text(0.15, 5.52, "Router R, dimension X.  Slot colors: gray = dedicated (private), "
            "blue = pooled, green = escape (DP-ESC, exempt).", fontsize=11.5, color="#566573")

    # router body
    ax.add_patch(FancyBboxPatch((2.05, 0.75), 7.1, 4.45, boxstyle="round,pad=0.08",
                                fc="#f8fbfd", ec=DARK, lw=2.0))
    ax.text(5.6, 4.92, "Router R", fontsize=13, weight="bold", color=DARK, ha="center")

    sw, sh, gap = 1.55, 0.5, 0.12
    ys = [1.0 + k * (sh + gap) for k in range(5)]
    for x0, name in ((2.6, "E-in  ($+x$)"), (7.05, "W-in  ($-x$)")):
        ax.text(x0 + sw / 2, ys[4] + sh + 0.18, name, ha="center", fontsize=12.5,
                weight="bold", color=DARK)
        box(ax, x0, ys[4], sw, sh, "esc", GREEN_F, GREEN_E, fs=10.5)
        box(ax, x0, ys[3], sw, sh, "P1", BLUE_F, BLUE_E, fs=10.5)
        box(ax, x0, ys[2], sw, sh, "P0", BLUE_F, BLUE_E, fs=10.5)
        box(ax, x0, ys[1], sw, sh, "D1", GRAY_F, GRAY_E, fs=10.5)
        box(ax, x0, ys[0], sw, sh, "D0", GRAY_F, GRAY_E, fs=10.5)

    # dashed pool envelope around the four pooled slots (both columns)
    y_lo, y_hi = ys[2] - 0.10, ys[3] + sh + 0.10
    ax.add_patch(Rectangle((2.40, y_lo), 6.4, y_hi - y_lo, fill=False,
                           ec=BLUE_E, lw=2.2, ls=(0, (5, 3))))
    ax.text(5.6, (y_lo + y_hi) / 2, "one pooled\nbudget:\nocc($E$)+occ($W$)\n$< S$",
            ha="center", va="center", fontsize=11.5, color=BLUE_E, weight="bold")

    # traffic arrows at pooled-band height
    ay = (y_lo + y_hi) / 2
    arrow(ax, (0.45, ay), (2.38, ay), color=RED_E, lw=5.0, ms=30)
    ax.text(1.35, ay + 0.35, "hot $+x$", color=RED_E, fontsize=13, weight="bold", ha="center")
    arrow(ax, (10.75, ay), (8.85, ay), color="#7fb3d5", lw=1.6, ms=16)
    ax.text(9.85, ay + 0.35, "cold $-x$", color="#7fb3d5", fontsize=13, ha="center")

    ax.text(5.6, 0.28, "Cold side idle  $\\Rightarrow$  hot side may hold up to all $S$ pooled units. "
            "Borrowing is emergent; no packet ever moves between buffers.",
            ha="center", fontsize=12, color=DARK, style="italic")
    save(fig, "dp_concept")


# ---------------------------------------------------------------- safety
def safety():
    fig, axs = plt.subplots(1, 2, figsize=(11.6, 4.4))
    for ax in axs:
        ax.set_xlim(0, 5.8); ax.set_ylim(0, 4.4); ax.axis("off")

    def layered(ax, title, top_txt, bot_txt, bot_fc, bot_ec, note):
        ax.text(2.9, 4.15, title, ha="center", fontsize=14.5, weight="bold", color=DARK)
        box(ax, 0.55, 2.45, 4.7, 1.05,
            top_txt, BLUE_F, BLUE_E, fs=11.5)
        box(ax, 0.55, 0.85, 4.7, 1.05, bot_txt, bot_fc, bot_ec, fs=11.5)
        arrow(ax, (2.9, 2.40), (2.9, 1.98), color=DARK, lw=2.6)
        ax.text(3.05, 2.16, "always eligible,\nnever capped", fontsize=10.5, color=DARK, va="center")
        ax.text(2.9, 0.32, note, ha="center", fontsize=10.5, color="#566573", style="italic")

    layered(axs[0], "DP-CBS  (depth-domain Duato)",
            "pooled window  [$r$, $V$)\nmay congest arbitrarily (cap $S$ only)",
            "dedicated window  [0, $r$)\nprivate CBS sub-ring keeps its bubble",
            GRAY_F, GRAY_E,
            "transit may fill the last free dedicated slot\nonly from a dedicated VC (bubble never leaks to the pool)")

    layered(axs[1], "DP-ESC  (Duato verbatim)",
            "adaptive window  [0, $V-1$)\nfully pooled, may congest arbitrarily",
            "escape VC  ($V-1$)\nexempt from pool; acyclic Mesh3D XYZ",
            GREEN_F, GREEN_E,
            "escape CDG untouched by DP\n$\\Rightarrow$ Duato's theorem applies unchanged")

    fig.suptitle("Safety composition: the pool is never in the deadlock-freedom path",
                 fontsize=13.5, color=DARK, y=0.02, va="bottom", style="italic")
    save(fig, "dp_safety")


# ---------------------------------------------------------------- checks
def checks():
    fig, ax = plt.subplots(figsize=(11.6, 3.9))
    ax.set_xlim(0, 11.6); ax.set_ylim(0, 3.9); ax.axis("off")

    ax.text(0.15, 3.62, "Where DP acts in the router pipeline", fontsize=16, weight="bold", color=DARK)

    y, h = 1.35, 0.85
    stages = [(0.4, 2.2, "RC\nroute compute"), (3.1, 2.2, "VA / SA\nVC + switch alloc"),
              (5.8, 2.2, "ST\ncrossbar traversal"), (8.5, 2.6, "downstream\ninport buffer")]
    for x, w, t in stages:
        box(ax, x, y, w, h, t, BLUE_F, BLUE_E, fs=11.5)
    for i in range(3):
        x_end = stages[i][0] + stages[i][1]
        arrow(ax, (x_end + 0.02, y + h / 2), (stages[i + 1][0] - 0.02, y + h / 2), lw=2.4)

    # DP-ESC callout above RC
    box(ax, 0.25, 2.65, 3.3, 0.72,
        "DP-ESC: skip outports whose\ndownstream pool is full", ORANGE_F, ORANGE_E, fs=10.5)
    arrow(ax, (1.5, 2.62), (1.5, y + h + 0.03), color=ORANGE_E, lw=2.0)

    # DP-CBS callout above SA
    box(ax, 3.75, 2.65, 4.2, 0.72,
        "DP-CBS: admit iff $\\mathit{pool\\_occ} < S$ (else dedicated/CBS);\nshared-first VC pick;  occ$++$ at grant", ORANGE_F, ORANGE_E, fs=10.5)
    arrow(ax, (4.6, 2.62), (4.6, y + h + 0.03), color=ORANGE_E, lw=2.0)

    # credit return
    arrow(ax, (9.8, y - 0.06), (4.6, 0.52), color=GREEN_E, lw=2.2, ls=(0, (5, 3)))
    ax.text(7.2, 0.42, "credit return (is_free_signal):  occ$--$", fontsize=11.5,
            color=GREEN_E, ha="center",
            bbox=dict(fc="white", ec="none", pad=1.0))
    ax.text(5.8, 0.02, "occupancy window = grant $\\rightarrow$ credit return (conservative: safety unaffected, only throughput)",
            fontsize=10.5, color="#566573", style="italic", ha="center")
    save(fig, "dp_check_placement")


concept()
safety()
checks()
