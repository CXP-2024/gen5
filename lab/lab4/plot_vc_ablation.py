#!/usr/bin/env python3
"""Plot the fixed-total-VC Lab 4 ablation results."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


TASK_DIR = Path(__file__).resolve().parent
RESULTS = TASK_DIR / "vc_ablation.csv"
PATTERNS = ("torus3d_transpose", "torus3d_xopposite")
PATTERN_LABELS = {
    "torus3d_transpose": "3D transpose",
    "torus3d_xopposite": "3D X-opposite",
}
COLORS = {0: "#7f7f7f", 1: "#009e73", 2: "#0072b2", 3: "#d55e00"}
MARKERS = {0: "x", 1: "^", 2: "s", 3: "o"}


def read_results() -> dict[tuple[str, int], list[dict[str, float]]]:
    grouped: dict[tuple[str, int], list[dict[str, float]]] = defaultdict(list)
    with RESULTS.open(newline="", encoding="utf-8") as csv_file:
        for raw in csv.DictReader(csv_file):
            escape_vcs = int(raw["escape_vcs"])
            row = {
                key: float(value)
                for key, value in raw.items()
                if key not in ("pattern", "deadlock_free_guarantee")
            }
            grouped[(raw["pattern"], escape_vcs)].append(row)
    for rows in grouped.values():
        rows.sort(key=lambda row: row["injection_rate"])
    missing = [
        f"{pattern}/E{escape_vcs}"
        for pattern in PATTERNS
        for escape_vcs in range(4)
        if (pattern, escape_vcs) not in grouped
    ]
    if missing:
        raise RuntimeError(f"missing ablation data: {', '.join(missing)}")
    return grouped


def label(escape_vcs: int) -> str:
    adaptive_vcs = 4 - escape_vcs
    suffix = " (unsafe)" if escape_vcs == 0 else ""
    return f"{adaptive_vcs} adaptive / {escape_vcs} escape{suffix}"


def style_axis(axis: plt.Axes) -> None:
    axis.grid(True, color="#d8dee4", linewidth=0.7, alpha=0.8)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)


def main() -> None:
    grouped = read_results()
    figure, axes = plt.subplots(
        2, 2, figsize=(10.5, 7.2), constrained_layout=True
    )
    for row, pattern in enumerate(PATTERNS):
        latency_axis, throughput_axis = axes[row]
        for escape_vcs in range(4):
            rows = grouped[(pattern, escape_vcs)]
            style = "--" if escape_vcs == 0 else "-"
            common = {
                "label": label(escape_vcs),
                "color": COLORS[escape_vcs],
                "marker": MARKERS[escape_vcs],
                "markersize": 4.0,
                "linewidth": 1.6,
                "linestyle": style,
            }
            rates = [point["injection_rate"] for point in rows]
            latency_axis.plot(
                rates, [point["packet_latency"] for point in rows], **common
            )
            throughput_axis.plot(
                rates, [point["throughput"] for point in rows], **common
            )
        latency_axis.set_title(f"{PATTERN_LABELS[pattern]}: latency")
        latency_axis.set_ylabel("Average packet latency (Ruby cycles)")
        throughput_axis.set_title(f"{PATTERN_LABELS[pattern]}: throughput")
        throughput_axis.set_ylabel("Packets/node/Ruby cycle")
        for axis in (latency_axis, throughput_axis):
            axis.set_xlabel("Injection rate (packets/node/system cycle)")
            style_axis(axis)
    axes[0, 0].legend(frameon=False, fontsize=8)
    for extension in ("png", "pdf"):
        figure.savefig(TASK_DIR / f"vc_ablation.{extension}", dpi=220)
    plt.close(figure)


if __name__ == "__main__":
    main()
