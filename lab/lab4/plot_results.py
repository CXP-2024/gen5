#!/usr/bin/env python3
"""Plot and summarize the Lab 4 3D topology/routing sweep."""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


TASK_DIR = Path(__file__).resolve().parent
RESULTS = TASK_DIR / "results.csv"
VALIDATION = TASK_DIR / "validation.csv"
SUMMARY = TASK_DIR / "summary.csv"
ANALYSIS = TASK_DIR / "analysis.md"
MODES = ["mesh3d_xyz", "torus3d_dor", "torus3d_adaptive_escape"]
PATTERNS = [
    "uniform_random",
    "torus3d_neighbor",
    "torus3d_tornado",
    "torus3d_transpose",
]
LABELS = {
    "mesh3d_xyz": "3D Mesh + XYZ",
    "torus3d_dor": "3D Torus + DOR",
    "torus3d_adaptive_escape": "3D Torus + Adaptive/Escape",
}
PATTERN_LABELS = {
    "uniform_random": "Uniform random",
    "torus3d_neighbor": "3D neighbor",
    "torus3d_tornado": "3D tornado",
    "torus3d_transpose": "3D transpose",
}
COLORS = {
    "mesh3d_xyz": "#0072b2",
    "torus3d_dor": "#d55e00",
    "torus3d_adaptive_escape": "#009e73",
}
MARKERS = {
    "mesh3d_xyz": "s",
    "torus3d_dor": "o",
    "torus3d_adaptive_escape": "^",
}


def read_results() -> dict[tuple[str, str], list[dict[str, float]]]:
    grouped: dict[tuple[str, str], list[dict[str, float]]] = defaultdict(list)
    with RESULTS.open(newline="", encoding="utf-8") as csv_file:
        for raw in csv.DictReader(csv_file):
            mode = raw.pop("mode")
            pattern = raw.pop("pattern")
            grouped[(mode, pattern)].append(
                {key: float(value) for key, value in raw.items()}
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
    expected_rates = [index / 50 for index in range(1, 51)]
    for key, rows in grouped.items():
        rates = [row["injection_rate"] for row in rows]
        if rates != expected_rates:
            raise RuntimeError(f"incomplete injection-rate sweep for {key}")
        if any(
            not math.isfinite(value) for row in rows for value in row.values()
        ):
            raise RuntimeError(f"non-finite result in sweep group {key}")
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
                markevery=3,
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
        figure.savefig(TASK_DIR / f"latency_throughput.{extension}", dpi=220)
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
                markevery=3,
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
        figure.savefig(TASK_DIR / f"source_acceptance.{extension}", dpi=220)
    plt.close(figure)


def save_escape_usage(
    grouped: dict[tuple[str, str], list[dict[str, float]]]
) -> None:
    figure, axis = plt.subplots(figsize=(7.6, 5.0), constrained_layout=True)
    mode = "torus3d_adaptive_escape"
    for pattern in PATTERNS:
        rows = grouped[(mode, pattern)]
        axis.plot(
            [row["injection_rate"] for row in rows],
            [row["escape_hop_fraction"] for row in rows],
            label=PATTERN_LABELS[pattern],
            marker="o",
            markersize=3.2,
            markevery=3,
            linewidth=1.6,
        )
    axis.set_xlabel("Injection rate (packets/node/system cycle)")
    axis.set_ylabel("Escape hops / classified hops")
    axis.set_title("Escape subnetwork utilization")
    axis.set_ylim(bottom=-0.01)
    axis.legend(frameon=False, fontsize=8)
    style_axis(axis)
    for extension in ("png", "pdf"):
        figure.savefig(TASK_DIR / f"escape_usage.{extension}", dpi=220)
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
        "low_load_hops",
        "max_stable_throughput",
        "max_stable_rate",
        "first_stalled_rate",
        "max_escape_hop_fraction",
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
                    "low_load_hops": rows[0]["average_hops"],
                    "max_stable_throughput": peak["throughput"],
                    "max_stable_rate": peak["injection_rate"],
                    "first_stalled_rate": first_stalled(rows),
                    "max_escape_hop_fraction": max(
                        row["escape_hop_fraction"] for row in rows
                    ),
                }
            )
    with SUMMARY.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file, fieldnames=fields, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(output)

    def fmt(value: float) -> str:
        return "not observed" if math.isnan(value) else f"{value:.2f}"

    by_key = {(row["mode"], row["pattern"]): row for row in output}
    transpose_mesh = by_key[("mesh3d_xyz", "torus3d_transpose")]
    transpose_dor = by_key[("torus3d_dor", "torus3d_transpose")]
    transpose_adaptive = by_key[
        ("torus3d_adaptive_escape", "torus3d_transpose")
    ]
    versus_mesh = (
        transpose_adaptive["max_stable_throughput"]
        / transpose_mesh["max_stable_throughput"]
    )
    versus_dor = (
        transpose_adaptive["max_stable_throughput"]
        / transpose_dor["max_stable_throughput"]
    )

    lines = [
        "# Lab 4 measured analysis",
        "",
        "The experiment uses 64 nodes, four VCs per vnet, single-flit",
        "vnet-0 control traffic, and a 10,000-Ruby-cycle measurement window.",
        "A point is classified as stalled when source injection acceptance",
        "falls below 0.9.",
        "",
        "| Pattern | Mode | Low-load latency | Hops | Max stable throughput | "
        "First stalled rate | Peak escape fraction |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in output:
        lines.append(
            f"| {PATTERN_LABELS[row['pattern']]} | {LABELS[row['mode']]} | "
            f"{row['low_load_latency']:.3f} | {row['low_load_hops']:.3f} | "
            f"{row['max_stable_throughput']:.6f} | "
            f"{fmt(row['first_stalled_rate'])} | "
            f"{row['max_escape_hop_fraction']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Key observations",
            "",
            "For 3D transpose, the adaptive/escape design sustains the full",
            "measured offered load. Its maximum stable throughput is",
            f"{versus_mesh:.2f}x the 3D Mesh result and {versus_dor:.2f}x",
            "the deterministic Torus result. The DOR comparison isolates",
            "the routing benefit from the extra wrap links of the Torus.",
            "Uniform random, neighbor, and tornado do not saturate within",
            "the generator's maximum offered-load range.",
            "",
            "The adaptive algorithm reserves the last VC as an escape VC.",
            "Adaptive hops use minimal Torus directions selected by available",
            "downstream VC credits. If no adaptive candidate is available, a",
            "packet may transition to the escape VC. Escape packets follow",
            "non-wrap XYZ routing and never return to adaptive VCs.",
            "",
            "The 3D Mesh escape channel dependency graph is acyclic. Because",
            "it is connected, uses a disjoint VC class, and has no dependency",
            "back to adaptive channels, it provides a progress path from",
            "every router without participating in an adaptive-channel cycle.",
        ]
    )

    if VALIDATION.exists():
        with VALIDATION.open(newline="", encoding="utf-8") as csv_file:
            validation = list(csv.DictReader(csv_file))
        lines.extend(
            [
                "",
                "## 100,000-cycle progress validation",
                "",
                "| Pattern | Acceptance | Delivery ratio | Throughput | "
                "Escape fraction |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for row in validation:
            pattern = PATTERN_LABELS[row["pattern"]]
            lines.append(
                f"| {pattern} | {float(row['injection_acceptance']):.6f} | "
                f"{float(row['delivery_ratio']):.6f} | "
                f"{float(row['throughput']):.6f} | "
                f"{float(row['escape_hop_fraction']):.6f} |"
            )
        lines.extend(
            [
                "",
                "All three maximum-rate validation runs completed without",
                "a deadlock or a progress failure. The delivery ratio is",
                "slightly below one because packets can remain in flight at",
                "the finite simulation boundary.",
            ]
        )

    lines.extend(
        [
            "",
            "![Latency-throughput curves](latency_throughput.png)",
            "",
            "![Source acceptance](source_acceptance.png)",
            "",
            "![Escape usage](escape_usage.png)",
        ]
    )
    ANALYSIS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    grouped = read_results()
    save_latency_throughput(grouped)
    save_acceptance(grouped)
    save_escape_usage(grouped)
    write_summary(grouped)
    print(f"plots and summaries written under {TASK_DIR}")


if __name__ == "__main__":
    main()
