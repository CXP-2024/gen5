#!/usr/bin/env python3
"""Plot and summarize the Lab 4 Topic 2 flow-control sweep."""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


TASK_DIR = Path(__file__).resolve().parent
RESULTS = TASK_DIR / "results_topic2.csv"
SUMMARY = TASK_DIR / "summary_topic2.csv"
MODES = ["torus3d_dor", "torus3d_dor_cbs", "torus3d_adaptive_escape"]
PATTERNS = [
    "uniform_random",
    "torus3d_neighbor",
    "torus3d_tornado",
    "torus3d_transpose",
]
LABELS = {
    "torus3d_dor": "DOR, no protection",
    "torus3d_dor_cbs": "DOR + CBS (ours)",
    "torus3d_adaptive_escape": "Adaptive + escape VC (Topic 1)",
}
PATTERN_LABELS = {
    "uniform_random": "Uniform random",
    "torus3d_neighbor": "3D neighbor",
    "torus3d_tornado": "3D tornado",
    "torus3d_transpose": "3D transpose",
}
COLORS = {
    "torus3d_dor": "#d55e00",
    "torus3d_dor_cbs": "#0072b2",
    "torus3d_adaptive_escape": "#009e73",
}
MARKERS = {
    "torus3d_dor": "o",
    "torus3d_dor_cbs": "s",
    "torus3d_adaptive_escape": "^",
}


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
    missing = [
        f"{mode}/{pattern}"
        for pattern in PATTERNS
        for mode in MODES
        if (mode, pattern) not in grouped
    ]
    if missing:
        raise RuntimeError(f"missing result groups: {', '.join(missing)}")
    return grouped


def stable(rows: list[dict[str, float]]) -> list[dict[str, float]]:
    return [row for row in rows if row["injection_acceptance"] >= 0.9]


def style_axis(axis: plt.Axes) -> None:
    axis.grid(True, color="#d8dee4", linewidth=0.7, alpha=0.8)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)


def save_latency_throughput(
    grouped: dict[tuple[str, str], list[dict[str, float]]]
) -> None:
    figure, axes = plt.subplots(
        2, 2, figsize=(10.5, 8.0), constrained_layout=True
    )
    for axis, pattern in zip(axes.flat, PATTERNS):
        for mode in MODES:
            rows = stable(grouped[(mode, pattern)])
            axis.plot(
                [row["throughput"] for row in rows],
                [row["packet_latency"] for row in rows],
                label=LABELS[mode],
                color=COLORS[mode],
                marker=MARKERS[mode],
                markersize=3.3,
                linewidth=1.6,
            )
            stalled = [
                row
                for row in grouped[(mode, pattern)]
                if row["injection_acceptance"] < 0.9
            ]
            if stalled:
                axis.scatter(
                    [row["throughput"] for row in stalled],
                    [row["packet_latency"] for row in stalled],
                    color=COLORS[mode],
                    marker="x",
                    s=35,
                    linewidth=1.5,
                )
        axis.set_title(PATTERN_LABELS[pattern])
        axis.set_xlabel("Throughput (packets/node/Ruby cycle)")
        axis.set_ylabel("Average packet latency (Ruby cycles)")
        style_axis(axis)
    axes[0, 0].legend(frameon=False, fontsize=8)
    for extension in ("png", "pdf"):
        figure.savefig(
            TASK_DIR / f"latency_throughput_topic2.{extension}", dpi=220
        )
    plt.close(figure)


def save_acceptance(
    grouped: dict[tuple[str, str], list[dict[str, float]]]
) -> None:
    figure, axes = plt.subplots(
        2, 2, figsize=(10.5, 7.8), constrained_layout=True
    )
    for axis, pattern in zip(axes.flat, PATTERNS):
        for mode in MODES:
            rows = grouped[(mode, pattern)]
            axis.plot(
                [row["injection_rate"] for row in rows],
                [row["injection_acceptance"] for row in rows],
                label=LABELS[mode],
                color=COLORS[mode],
                marker=MARKERS[mode],
                markersize=3.3,
                linewidth=1.6,
            )
        axis.axhline(0.9, color="#555555", linestyle="--", linewidth=1)
        axis.set_title(PATTERN_LABELS[pattern])
        axis.set_xlabel("Injection rate (packets/node/system cycle)")
        axis.set_ylabel("Injected / expected")
        axis.set_ylim(-0.02, 1.08)
        style_axis(axis)
    axes[0, 0].legend(frameon=False, fontsize=8)
    for extension in ("png", "pdf"):
        figure.savefig(
            TASK_DIR / f"source_acceptance_topic2.{extension}", dpi=220
        )
    plt.close(figure)


def save_cbs_activity(
    grouped: dict[tuple[str, str], list[dict[str, float]]]
) -> None:
    figure, axes = plt.subplots(
        1, 2, figsize=(10.5, 4.4), constrained_layout=True
    )
    mode = "torus3d_dor_cbs"
    for axis, stat, title in zip(
        axes,
        ("cbs_entry_blocks", "cbs_mark_moves"),
        ("Ring-entry stalls caused by the critical bubble",
         "Critical-bubble displacements"),
    ):
        for pattern in PATTERNS:
            rows = grouped[(mode, pattern)]
            axis.plot(
                [row["injection_rate"] for row in rows],
                [row[stat] for row in rows],
                label=PATTERN_LABELS[pattern],
                marker="o",
                markersize=3.2,
                linewidth=1.6,
            )
        axis.set_xlabel("Injection rate (packets/node/system cycle)")
        axis.set_ylabel(f"{stat} (count)")
        axis.set_title(title)
        style_axis(axis)
    axes[0].legend(frameon=False, fontsize=8)
    for extension in ("png", "pdf"):
        figure.savefig(TASK_DIR / f"cbs_activity.{extension}", dpi=220)
    plt.close(figure)


def first_stalled(rows: list[dict[str, float]]) -> float:
    for row in rows:
        if row["injection_acceptance"] < 0.9:
            return row["injection_rate"]
    return math.nan


def write_summary(
    grouped: dict[tuple[str, str], list[dict[str, float]]]
) -> None:
    fields = [
        "mode",
        "pattern",
        "low_load_latency",
        "max_stable_throughput",
        "max_stable_rate",
        "first_stalled_rate",
        "max_cbs_entry_blocks",
        "max_cbs_mark_moves",
    ]
    output = []
    for pattern in PATTERNS:
        for mode in MODES:
            rows = grouped[(mode, pattern)]
            stable_rows = stable(rows)
            peak = max(stable_rows, key=lambda row: row["throughput"])
            output.append(
                {
                    "mode": mode,
                    "pattern": pattern,
                    "low_load_latency": rows[0]["packet_latency"],
                    "max_stable_throughput": peak["throughput"],
                    "max_stable_rate": peak["injection_rate"],
                    "first_stalled_rate": first_stalled(rows),
                    "max_cbs_entry_blocks": max(
                        row["cbs_entry_blocks"] for row in rows
                    ),
                    "max_cbs_mark_moves": max(
                        row["cbs_mark_moves"] for row in rows
                    ),
                }
            )
    with SUMMARY.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file, fieldnames=fields, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(output)


def main() -> None:
    grouped = read_results()
    save_latency_throughput(grouped)
    save_acceptance(grouped)
    save_cbs_activity(grouped)
    write_summary(grouped)
    print(f"plots and summaries written under {TASK_DIR}")


if __name__ == "__main__":
    main()
