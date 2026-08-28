#!/usr/bin/env python3
"""Report-quality experiment figures for the DP report (large fonts, few
curves). Reads experiments/batch2_dp_main_sweep/{results_dp,gains_dp}.csv.
Outputs: fig_lt_headline.pdf, fig_gains_bar.pdf, fig_activity.pdf (+ .png)."""

import csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({
    "font.size": 13.5, "axes.labelsize": 14, "axes.titlesize": 15,
    "legend.fontsize": 12, "xtick.labelsize": 12.5, "ytick.labelsize": 12.5,
    "lines.linewidth": 2.4, "lines.markersize": 7, "font.family": "DejaVu Sans",
})

C_BASE, C_DP, C_NEG = "#5d6d7e", "#1f618d", "#c0392b"
CEIL = 0.49  # dp_peak above this = at the 0.5 offered-load ceiling

RESULTS = "experiments/batch2_dp_main_sweep/results_dp.csv"
GAINS = "experiments/batch2_dp_main_sweep/gains_dp.csv"

rows = list(csv.DictReader(open(RESULTS)))
gains = list(csv.DictReader(open(GAINS)))


def series(mode, pattern):
    pts = [(float(r["throughput"]), float(r["packet_latency"]), float(r["injection_acceptance"]))
           for r in rows if r["mode"] == mode and r["pattern"] == pattern]
    if not pts:
        raise SystemExit(f"no data for {mode}/{pattern}")
    pts.sort()
    stable = [(t, l) for t, l, a in pts if a >= 0.9]
    return pts, stable


def gain_row(comp, pattern):
    for g in gains:
        if g["comparison"] == comp and g["pattern"] == pattern:
            return g
    raise SystemExit(f"no gain row {comp}/{pattern}")


# -------------------------------------------------- fig 1: headline curves
def lt_headline():
    fig, axs = plt.subplots(1, 2, figsize=(11.0, 4.5))
    panels = [
        ("B C=6", "torus3d_xopposite", "Family B, $C{=}6$, xopposite",
         "Baseline: adaptive+escape, vcs=3", "DP-ESC: vcs=5, $S{=}4$"),
        ("A C=6", "torus3d_xopposite", "Family A, $C{=}6$, xopposite",
         "Baseline: DOR+CBS, vcs=3", "DP-CBS: vcs=4, $r{=}2$, $S{=}2$"),
    ]
    for ax, (comp, pat, title, blab, dlab) in zip(axs, panels):
        g = gain_row(comp, pat)
        peaks = []
        for mode, lab, color, mk in ((g["baseline_mode"], blab, C_BASE, "o"),
                                     (g["dp_mode"], dlab, C_DP, "s")):
            _, stable = series(mode, pat)
            # stable region only: past saturation, throughput folds back and
            # the curve zigzags — the dotted peak line tells that story instead
            ax.plot([t for t, _ in stable], [l for _, l in stable],
                    color=color, marker=mk, label=lab,
                    ls="--" if color == C_BASE else "-")
            peak = max(t for t, _ in stable)
            peaks.append(peak)
            ax.axvline(peak, color=color, ls=":", lw=1.6)
            ax.annotate(f"{peak:.3f}", (peak, 40 if color == C_BASE else 52),
                        fontsize=12.5, color=color,
                        ha="right" if color == C_BASE else "left",
                        xytext=(-4 if color == C_BASE else 4, 0), textcoords="offset points")
        ax.set_ylim(0, 60)
        ax.set_xlim(0, max(peaks) * 1.14)
        ax.set_xlabel("throughput (packets/node/cycle)")
        ax.set_title(f"{title}  ({float(g['gain_percent']):+.1f}%)")
        ax.grid(alpha=0.3)
        ax.legend(loc="upper left", framealpha=0.95)
    axs[0].set_ylabel("avg packet latency (cycles)")
    fig.tight_layout()
    fig.savefig("fig_lt_headline.pdf", bbox_inches="tight")
    fig.savefig("fig_lt_headline.png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    print("wrote fig_lt_headline.pdf")


# -------------------------------------------------- fig 2: gains bar chart
PAT_SHORT = {"torus3d_xopposite": "xopposite", "torus3d_tornado": "tornado",
             "torus3d_transpose": "transpose", "torus3d_neighbor": "neighbor",
             "uniform_random": "uniform"}


def bar_panel(ax, cells, title):
    """cells: list of (label, gain%, lower_bound?)"""
    xs = range(len(cells))
    for x, (lab, val, lb) in zip(xs, cells):
        color = C_DP if val >= 0 else C_NEG
        ax.bar(x, val, 0.62, color=color, hatch="//" if lb else None,
               edgecolor="white", zorder=3)
        pre = "$\\geq$" if lb else ""
        ax.annotate(f"{pre}{val:+.1f}%", (x, val), ha="center", fontsize=12.5,
                    xytext=(0, 5 if val >= 0 else -17), textcoords="offset points",
                    weight="bold", color=color)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([c[0] for c in cells], fontsize=12)
    ax.axhline(0, color=DARK_AX, lw=1.0)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3, zorder=0)


DARK_AX = "#2c3e50"


def gains_bar():
    fig, axs = plt.subplots(1, 2, figsize=(11.0, 4.2),
                            gridspec_kw={"width_ratios": [5, 5]})
    b_cells = []
    for pat in ("torus3d_xopposite", "torus3d_tornado", "torus3d_transpose",
                "torus3d_neighbor", "uniform_random"):
        g = gain_row("B C=6", pat)
        b_cells.append((PAT_SHORT[pat], float(g["gain_percent"]),
                        float(g["dp_peak"]) > CEIL))
    bar_panel(axs[0], b_cells, "DP-ESC vs. baseline, $C{=}6$ (hatched = lower bound)")

    a_cells = []
    for comp, pat, lab in (("A C=6", "torus3d_xopposite", "xopp\n$C{=}6$"),
                           ("A C=6", "torus3d_transpose", "transp\n$C{=}6$"),
                           ("A C=6", "uniform_random", "unif\n$C{=}6$"),
                           ("A C=8", "torus3d_xopposite", "xopp\n$C{=}8$"),
                           ("A C=8", "torus3d_transpose", "transp\n$C{=}8$")):
        g = gain_row(comp, pat)
        a_cells.append((lab, float(g["gain_percent"]), float(g["dp_peak"]) > CEIL))
    bar_panel(axs[1], a_cells, "DP-CBS vs. baseline (informative cells)")

    axs[0].set_ylabel("peak stable throughput gain (%)")
    axs[0].set_ylim(0, 38)
    axs[1].set_ylim(-8, 26)
    fig.tight_layout()
    fig.savefig("fig_gains_bar.pdf", bbox_inches="tight")
    fig.savefig("fig_gains_bar.png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    print("wrote fig_gains_bar.pdf")


# -------------------------------------------------- fig 3: pool activity
def activity():
    fig, axs = plt.subplots(1, 2, figsize=(11.0, 4.2))
    panels = [
        (gain_row("A C=6", "torus3d_transpose")["dp_mode"], "torus3d_transpose",
         "DP-CBS (A2), transpose (two-sided)"),
        (gain_row("B C=6", "torus3d_tornado")["dp_mode"], "torus3d_tornado",
         "DP-ESC (B4), tornado"),
    ]
    for ax, (mode, pat, title) in zip(axs, panels):
        data = [(float(r["injection_rate"]), float(r["dp_shared_grants"]),
                 float(r["dp_pool_blocks"]))
                for r in rows if r["mode"] == mode and r["pattern"] == pat]
        data.sort()
        xs = [d[0] for d in data]
        ax.plot(xs, [d[1] / 1e3 for d in data], color=C_DP, marker="o",
                label="dp_shared_grants")
        ax.plot(xs, [d[2] / 1e3 for d in data], color=C_NEG, marker="s", ls="--",
                label="dp_pool_blocks")
        ax.set_title(title)
        ax.set_xlabel("injection rate (packets/node/cycle)")
        ax.grid(alpha=0.3)
        ax.legend(loc="upper left", framealpha=0.95)
    axs[0].set_ylabel("events per 10k-cycle run ($\\times 10^3$)")
    axs[1].annotate("$\\equiv 0$ by construction\n(route-time filter)",
                    xy=(0.62, 0.10), xycoords="axes fraction", fontsize=12,
                    color=C_NEG, ha="center")
    fig.tight_layout()
    fig.savefig("fig_activity.pdf", bbox_inches="tight")
    fig.savefig("fig_activity.png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    print("wrote fig_activity.pdf")


lt_headline()
gains_bar()
activity()
