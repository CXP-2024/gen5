#!/usr/bin/env python3
"""Plot and summarize the Lab 4 Topic 2 Dimension Pool (DP) sweep.

Reads results_dp.csv (written by run_sweep_dp.py) and produces:
  latency_throughput_dp_a.{png,pdf}   family A (DOR+CBS), one panel/pattern
  latency_throughput_dp_b.{png,pdf}   family B (adaptive+escape)
  source_acceptance_dp_a.{png,pdf}    injected/expected vs offered rate
  source_acceptance_dp_b.{png,pdf}
  dp_activity.{png,pdf}               dp_shared_grants / dp_pool_blocks
  summary_dp.csv                      per (mode, pattern) digest
  gains_dp.csv                        DP vs equal-storage baseline deltas

Equal-storage pairs share a color; the baseline is dashed, DP is solid.
Only patterns present in the CSV are plotted, so the script can run on a
partially completed sweep.
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


TASK_DIR = Path(__file__).resolve().parent
RESULTS = TASK_DIR / "results_dp.csv"
SUMMARY = TASK_DIR / "summary_dp.csv"
GAINS = TASK_DIR / "gains_dp.csv"

FAMILY_A = ["A1_cbs_v3", "A2_dpcbs_v4_s2", "A3_cbs_v4", "A4_dpcbs_v6_s4"]
FAMILY_B = [
    "B1_esc_v2", "B2_dpesc_v3_s2", "B3_esc_v3",
    "B4_dpesc_v5_s4", "B5_esc_v4", "B6_dpesc_v7_s6",
]
MODES = FAMILY_A + FAMILY_B
DP_MODES = [mode for mode in MODES if "dp" in mode]

# (baseline, dp) pairs with equal usable storage per dimension pair,
# plus the equal-VC-count honest comparisons.
STORAGE_PAIRS = [
    ("A1_cbs_v3", "A2_dpcbs_v4_s2", "A C=6"),
    ("A3_cbs_v4", "A4_dpcbs_v6_s4", "A C=8"),
    ("B1_esc_v2", "B2_dpesc_v3_s2", "B C=4"),
    ("B3_esc_v3", "B4_dpesc_v5_s4", "B C=6"),
    ("B5_esc_v4", "B6_dpesc_v7_s6", "B C=8"),
]
EQUAL_VC_PAIRS = [
    ("A3_cbs_v4", "A2_dpcbs_v4_s2", "A vcs=4"),
    ("B3_esc_v3", "B2_dpesc_v3_s2", "B vcs=3"),
    ("B5_esc_v4", "B4_dpesc_v5_s4", "B vcs=4/5"),
]

PATTERNS = [
    "torus3d_xopposite",
    "torus3d_tornado",
    "torus3d_transpose",
    "torus3d_neighbor",
    "uniform_random",
]
PATTERN_LABELS = {
    "torus3d_xopposite": "X-opposite (one-sided ring)",
    "torus3d_tornado": "3D tornado",
    "torus3d_transpose": "3D transpose",
    "torus3d_neighbor": "3D neighbor",
    "uniform_random": "Uniform random",
}
LABELS = {
    "A1_cbs_v3": "CBS vcs=3 (C=6)",
    "A2_dpcbs_v4_s2": "DP-CBS vcs=4 r=2 S=2 (C=6, ours)",
    "A3_cbs_v4": "CBS vcs=4 (C=8)",
    "A4_dpcbs_v6_s4": "DP-CBS vcs=6 r=2 S=4 (C=8, ours)",
    "B1_esc_v2": "Escape vcs=2 (C=4)",
    "B2_dpesc_v3_s2": "DP-ESC vcs=3 S=2 (C=4, ours)",
    "B3_esc_v3": "Escape vcs=3 (C=6)",
    "B4_dpesc_v5_s4": "DP-ESC vcs=5 S=4 (C=6, ours)",
    "B5_esc_v4": "Escape vcs=4 (C=8)",
    "B6_dpesc_v7_s6": "DP-ESC vcs=7 S=6 (C=8, ours)",
}
PAIR_COLORS = ["#0072b2", "#d55e00", "#009e73"]
STYLE = {}
for index, (baseline, dp_mode, _) in enumerate(STORAGE_PAIRS):
    color = PAIR_COLORS[index % len(PAIR_COLORS)]
    STYLE[baseline] = (color, "--", "o")
    STYLE[dp_mode] = (color, "-", "s")


def read_results() -> dict[tuple[str, str], list[dict[str, float]]]:
    grouped: dict[tuple[str, str], list[dict[str, float]]] = defaultdict(list)
    with RESULTS.open(newline="", encoding="utf-8") as csv_file:
        for raw in csv.DictReader(csv_file):
            mode = raw.pop("mode")
            pattern = raw.pop("pattern")
            grouped[(mode, pattern)].append(
                {
                    key: float(value) if value else math.nan
                    for key, value in raw.items()
                }
            )
    for rows in grouped.values():
        rows.sort(key=lambda row: row["injection_rate"])
    return grouped


def available_patterns(
    grouped: dict[tuple[str, str], list[dict[str, float]]]
) -> list[str]:
    return [
        pattern
        for pattern in PATTERNS
        if all((mode, pattern) in grouped for mode in MODES)
    ]


def stable(rows: list[dict[str, float]]) -> list[dict[str, float]]:
    return [
        row
        for row in rows
        if row["injection_acceptance"] >= 0.9 and not row["deadlock"]
    ]


def style_axis(axis: plt.Axes) -> None:
    axis.grid(True, color="#d8dee4", linewidth=0.7, alpha=0.8)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)


def panel_grid(count: int) -> tuple[plt.Figure, list[plt.Axes]]:
    columns = 3 if count > 4 else 2
    row_count = math.ceil(count / columns)
    figure, axes = plt.subplots(
        row_count,
        columns,
        figsize=(3.6 * columns + 0.6, 3.4 * row_count + 0.4),
        constrained_layout=True,
    )
    flat = list(axes.flat) if count > 1 else [axes]
    for axis in flat[count:]:
        axis.set_visible(False)
    return figure, flat[:count]


def save_latency_throughput(
    grouped: dict[tuple[str, str], list[dict[str, float]]],
    patterns: list[str],
    modes: list[str],
    stem: str,
) -> None:
    figure, axes = panel_grid(len(patterns))
    for axis, pattern in zip(axes, patterns):
        stable_latencies = [
            row["packet_latency"]
            for mode in modes
            for row in stable(grouped[(mode, pattern)])
            if not math.isnan(row["packet_latency"])
        ]
        # Keep the saturation knee readable: cap the axis near the stable
        # curves and pin unstable markers to the top edge.
        y_top = max(stable_latencies, default=50.0) * 1.25 + 10.0
        for mode in modes:
            color, linestyle, marker = STYLE[mode]
            rows = stable(grouped[(mode, pattern)])
            axis.plot(
                [row["throughput"] for row in rows],
                [row["packet_latency"] for row in rows],
                label=LABELS[mode],
                color=color,
                linestyle=linestyle,
                marker=marker,
                markersize=3.0,
                linewidth=1.5,
            )
            unstable = [
                row
                for row in grouped[(mode, pattern)]
                if row["injection_acceptance"] < 0.9 or row["deadlock"]
            ]
            if unstable:
                axis.scatter(
                    [row["throughput"] for row in unstable],
                    [
                        min(row["packet_latency"], y_top * 0.97)
                        for row in unstable
                    ],
                    color=color,
                    marker="x",
                    s=30,
                    linewidth=1.3,
                )
        axis.set_ylim(0, y_top)
        axis.set_title(PATTERN_LABELS[pattern], fontsize=10)
        axis.set_xlabel("Throughput (packets/node/Ruby cycle)")
        axis.set_ylabel("Avg packet latency (Ruby cycles)")
        style_axis(axis)
    axes[0].legend(frameon=False, fontsize=7)
    for extension in ("png", "pdf"):
        figure.savefig(TASK_DIR / f"{stem}.{extension}", dpi=220)
    plt.close(figure)


def save_acceptance(
    grouped: dict[tuple[str, str], list[dict[str, float]]],
    patterns: list[str],
    modes: list[str],
    stem: str,
) -> None:
    figure, axes = panel_grid(len(patterns))
    for axis, pattern in zip(axes, patterns):
        for mode in modes:
            color, linestyle, marker = STYLE[mode]
            rows = grouped[(mode, pattern)]
            axis.plot(
                [row["injection_rate"] for row in rows],
                [row["injection_acceptance"] for row in rows],
                label=LABELS[mode],
                color=color,
                linestyle=linestyle,
                marker=marker,
                markersize=3.0,
                linewidth=1.5,
            )
        axis.axhline(0.9, color="#555555", linestyle=":", linewidth=1)
        axis.set_title(PATTERN_LABELS[pattern], fontsize=10)
        axis.set_xlabel("Injection rate (packets/node/system cycle)")
        axis.set_ylabel("Injected / expected")
        axis.set_ylim(-0.02, 1.08)
        style_axis(axis)
    axes[0].legend(frameon=False, fontsize=7)
    for extension in ("png", "pdf"):
        figure.savefig(TASK_DIR / f"{stem}.{extension}", dpi=220)
    plt.close(figure)


def save_dp_activity(
    grouped: dict[tuple[str, str], list[dict[str, float]]],
    patterns: list[str],
) -> None:
    figure, axes = plt.subplots(
        2,
        len(patterns),
        figsize=(3.2 * len(patterns) + 0.6, 6.6),
        constrained_layout=True,
        squeeze=False,
    )
    for column, pattern in enumerate(patterns):
        for row_index, stat in enumerate(
            ("dp_shared_grants", "dp_pool_blocks")
        ):
            axis = axes[row_index][column]
            for mode in DP_MODES:
                color, _, marker = STYLE[mode]
                rows = grouped[(mode, pattern)]
                axis.plot(
                    [point["injection_rate"] for point in rows],
                    [point[stat] for point in rows],
                    label=LABELS[mode],
                    color=color,
                    linestyle="-" if mode.startswith("A") else "-.",
                    marker=marker,
                    markersize=2.8,
                    linewidth=1.4,
                )
            axis.set_title(
                f"{PATTERN_LABELS[pattern]}\n{stat}", fontsize=9
            )
            axis.set_xlabel("Injection rate")
            axis.set_ylabel("count")
            style_axis(axis)
    axes[0][0].legend(frameon=False, fontsize=6.5)
    for extension in ("png", "pdf"):
        figure.savefig(TASK_DIR / f"dp_activity.{extension}", dpi=220)
    plt.close(figure)


def peak_throughput(rows: list[dict[str, float]]) -> tuple[float, float]:
    stable_rows = stable(rows)
    if not stable_rows:
        return math.nan, math.nan
    peak = max(stable_rows, key=lambda row: row["throughput"])
    return peak["throughput"], peak["injection_rate"]


def first_unstable(rows: list[dict[str, float]]) -> float:
    for row in rows:
        if row["injection_acceptance"] < 0.9 or row["deadlock"]:
            return row["injection_rate"]
    return math.nan


def write_summary(
    grouped: dict[tuple[str, str], list[dict[str, float]]],
    patterns: list[str],
) -> None:
    fields = [
        "mode",
        "pattern",
        "low_load_latency",
        "max_stable_throughput",
        "max_stable_rate",
        "first_unstable_rate",
        "deadlocks",
        "max_dp_shared_grants",
        "max_dp_pool_blocks",
        "max_cbs_entry_blocks",
        "max_escape_transitions",
    ]
    output = []
    for pattern in patterns:
        for mode in MODES:
            rows = grouped[(mode, pattern)]
            throughput, rate = peak_throughput(rows)
            output.append(
                {
                    "mode": mode,
                    "pattern": pattern,
                    "low_load_latency": rows[0]["packet_latency"],
                    "max_stable_throughput": throughput,
                    "max_stable_rate": rate,
                    "first_unstable_rate": first_unstable(rows),
                    "deadlocks": sum(int(row["deadlock"]) for row in rows),
                    "max_dp_shared_grants": max(
                        row["dp_shared_grants"] for row in rows
                    ),
                    "max_dp_pool_blocks": max(
                        row["dp_pool_blocks"] for row in rows
                    ),
                    "max_cbs_entry_blocks": max(
                        row["cbs_entry_blocks"] for row in rows
                    ),
                    "max_escape_transitions": max(
                        row["escape_transitions"] for row in rows
                    ),
                }
            )
    with SUMMARY.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file, fieldnames=fields, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(output)


def write_gains(
    grouped: dict[tuple[str, str], list[dict[str, float]]],
    patterns: list[str],
) -> None:
    fields = [
        "comparison",
        "kind",
        "pattern",
        "baseline_mode",
        "dp_mode",
        "baseline_peak",
        "dp_peak",
        "gain_percent",
    ]
    output = []
    for kind, pairs in (
        ("equal_storage", STORAGE_PAIRS),
        ("equal_vcs", EQUAL_VC_PAIRS),
    ):
        for baseline, dp_mode, tag in pairs:
            for pattern in patterns:
                base_peak, _ = peak_throughput(grouped[(baseline, pattern)])
                dp_peak, _ = peak_throughput(grouped[(dp_mode, pattern)])
                gain = (
                    (dp_peak - base_peak) / base_peak * 100
                    if base_peak and not math.isnan(base_peak)
                    else math.nan
                )
                output.append(
                    {
                        "comparison": tag,
                        "kind": kind,
                        "pattern": pattern,
                        "baseline_mode": baseline,
                        "dp_mode": dp_mode,
                        "baseline_peak": base_peak,
                        "dp_peak": dp_peak,
                        "gain_percent": gain,
                    }
                )
    with GAINS.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file, fieldnames=fields, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(output)


def main() -> None:
    grouped = read_results()
    patterns = available_patterns(grouped)
    if not patterns:
        raise SystemExit("no complete pattern found in results_dp.csv yet")
    save_latency_throughput(
        grouped, patterns, FAMILY_A, "latency_throughput_dp_a"
    )
    save_latency_throughput(
        grouped, patterns, FAMILY_B, "latency_throughput_dp_b"
    )
    save_acceptance(grouped, patterns, FAMILY_A, "source_acceptance_dp_a")
    save_acceptance(grouped, patterns, FAMILY_B, "source_acceptance_dp_b")
    save_dp_activity(grouped, patterns)
    write_summary(grouped, patterns)
    write_gains(grouped, patterns)
    print(
        f"plots and summaries written under {TASK_DIR} "
        f"for patterns: {', '.join(patterns)}"
    )


if __name__ == "__main__":
    main()
