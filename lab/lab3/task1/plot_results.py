#!/usr/bin/env python3
"""Plot and summarize the Lab 3 Task 1 topology sweep."""

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
SUMMARY = TASK_DIR / "summary.csv"
ANALYSIS = TASK_DIR / "analysis.md"
TOPOLOGIES = ["ring", "mesh"]
LABELS = {"ring": "16-node Ring", "mesh": "4x4 Mesh"}
COLORS = {"ring": "#d55e00", "mesh": "#0072b2"}
MARKERS = {"ring": "o", "mesh": "s"}
THEORETICAL_HOPS = {"ring": 4.0, "mesh": 2.5}


def read_results() -> dict[str, list[dict[str, float]]]:
    grouped: dict[str, list[dict[str, float]]] = defaultdict(list)
    with RESULTS.open(newline="", encoding="utf-8") as csv_file:
        for raw in csv.DictReader(csv_file):
            topology = raw.pop("topology")
            grouped[topology].append(
                {key: float(value) for key, value in raw.items()}
            )
    for rows in grouped.values():
        rows.sort(key=lambda row: row["injection_rate"])
    missing = [name for name in TOPOLOGIES if name not in grouped]
    if missing:
        raise RuntimeError(f"missing topologies: {', '.join(missing)}")
    return grouped


def style_axis(axis: plt.Axes) -> None:
    axis.grid(True, color="#d8dee4", linewidth=0.7, alpha=0.8)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)


def stable_rows(rows: list[dict[str, float]]) -> list[dict[str, float]]:
    return [row for row in rows if row["injection_acceptance"] >= 0.9]


def save_latency_throughput(
    grouped: dict[str, list[dict[str, float]]]
) -> None:
    figure, axis = plt.subplots(figsize=(7.5, 5.0), constrained_layout=True)
    for topology in TOPOLOGIES:
        rows = stable_rows(grouped[topology])
        axis.plot(
            [row["throughput"] for row in rows],
            [row["packet_latency"] for row in rows],
            label=LABELS[topology],
            color=COLORS[topology],
            marker=MARKERS[topology],
            markersize=3.5,
            markevery=3,
            linewidth=1.7,
        )
        stalled = [
            row
            for row in grouped[topology]
            if row["injection_acceptance"] < 0.9
        ]
        if stalled:
            axis.scatter(
                [row["throughput"] for row in stalled],
                [row["packet_latency"] for row in stalled],
                label=f"{LABELS[topology]} stalled",
                color=COLORS[topology],
                marker="x",
                s=55,
                linewidth=2,
            )
    axis.set_xlabel("Achieved throughput (packets/node/Ruby cycle)")
    axis.set_ylabel("Average packet latency (Ruby cycles)")
    axis.set_title("Uniform Random: Ring vs. 4x4 Mesh")
    axis.legend(frameon=False)
    style_axis(axis)
    for extension in ("png", "pdf"):
        figure.savefig(TASK_DIR / f"latency_throughput.{extension}", dpi=220)
    plt.close(figure)


def save_injection_response(
    grouped: dict[str, list[dict[str, float]]]
) -> None:
    figure, axes = plt.subplots(
        1, 2, figsize=(10.5, 4.2), constrained_layout=True
    )
    for topology in TOPOLOGIES:
        rows = grouped[topology]
        for axis, key in zip(axes, ("throughput", "injection_acceptance")):
            axis.plot(
                [row["injection_rate"] for row in rows],
                [row[key] for row in rows],
                label=LABELS[topology],
                color=COLORS[topology],
                marker=MARKERS[topology],
                markersize=3.2,
                markevery=3,
                linewidth=1.6,
            )
    axes[0].plot(
        [0.01, 0.50],
        [0.005, 0.25],
        color="#555555",
        linestyle="--",
        linewidth=1.2,
        label="Offered load",
    )
    axes[0].set_title("Throughput response")
    axes[0].set_ylabel("packets/node/Ruby cycle")
    axes[1].set_title("Source injection acceptance")
    axes[1].set_ylabel("injected / expected generated")
    axes[1].set_ylim(-0.02, 1.08)
    for axis in axes:
        axis.set_xlabel("Injection rate (packets/node/system cycle)")
        axis.legend(frameon=False, fontsize=8)
        style_axis(axis)
    for extension in ("png", "pdf"):
        figure.savefig(TASK_DIR / f"injection_response.{extension}", dpi=220)
    plt.close(figure)


def first_stalled(rows: list[dict[str, float]]) -> float:
    for row in rows:
        if row["injection_acceptance"] < 0.9:
            return row["injection_rate"]
    return math.nan


def write_summary(grouped: dict[str, list[dict[str, float]]]) -> None:
    fields = [
        "topology",
        "low_load_latency",
        "measured_hops",
        "theoretical_hops",
        "max_stable_throughput",
        "max_stable_injection_rate",
        "first_stalled_rate",
    ]
    output = []
    for topology in TOPOLOGIES:
        rows = grouped[topology]
        stable = stable_rows(rows)
        peak = max(stable, key=lambda row: row["throughput"])
        output.append(
            {
                "topology": topology,
                "low_load_latency": rows[0]["packet_latency"],
                "measured_hops": rows[0]["average_hops"],
                "theoretical_hops": THEORETICAL_HOPS[topology],
                "max_stable_throughput": peak["throughput"],
                "max_stable_injection_rate": peak["injection_rate"],
                "first_stalled_rate": first_stalled(rows),
            }
        )
    with SUMMARY.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file, fieldnames=fields, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(output)

    index = {row["topology"]: row for row in output}
    ring_last = grouped["ring"][-1]
    stalled_display = (
        "not observed"
        if math.isnan(index["ring"]["first_stalled_rate"])
        else f"{index['ring']['first_stalled_rate']:.2f}"
    )
    lines = [
        "# Lab 3 Task 1 analysis",
        "",
        "## Implementation and validation",
        "",
        "`configs/topologies/Ring.py` creates 16 routers, 32 directed internal",
        "links, and 32 controller-facing external links. Clockwise and",
        "counterclockwise wraparound links connect routers 15 and 0. Custom",
        "routing (`--routing-algorithm=2`) compares modular distance in both",
        "directions and chooses the shorter path; an eight-hop tie goes clockwise.",
        "Directed tests produced exactly 1, 1, 8, and 5 hops for routes 0->15,",
        "15->0, 0->8, and 3->14.",
        "",
        "## Low-load behavior",
        "",
        f"The Ring measures {index['ring']['measured_hops']:.3f} average hops at rate "
        f"0.01 versus the exact uniform-random expectation of 4.0. The 4x4 Mesh",
        f"measures {index['mesh']['measured_hops']:.3f} versus 2.5. Corresponding",
        f"packet latencies are {index['ring']['low_load_latency']:.3f} and",
        f"{index['mesh']['low_load_latency']:.3f} Ruby cycles. The Ring is slower",
        "because its degree-two topology has longer paths than the two-dimensional",
        "Mesh.",
        "",
        "## Throughput and cyclic dependency",
        "",
        f"The largest stable Ring throughput observed is "
        f"{index['ring']['max_stable_throughput']:.6f} packets/node/Ruby cycle at",
        f"injection rate {index['ring']['max_stable_injection_rate']:.2f}. The first",
        f"stalled point is rate {stalled_display}. At rate 0.50, only",
        f"{ring_last['injection_acceptance']:.3f} of expected packets enter the",
        "network, so received/injected alone would hide the source-side stall.",
        "Minimal routing in each direction forms a cyclic channel-dependency graph",
        "around the Ring. With finite one-flit control buffers and four VCs, a high",
        "load can fill the cycle so every flit waits for downstream credit. This is",
        "a routing-level deadlock hazard rather than an ordinary smooth saturation",
        "point. Whether a finite run closes the dependency cycle depends on packet",
        "timing, explaining why an isolated higher-rate point may complete after a",
        "lower-rate point stalls. Strict deadlock freedom requires a dateline/escape-VC",
        "scheme or",
        "another mechanism that breaks the cyclic dependency.",
        "",
        "![Latency-throughput comparison](latency_throughput.png)",
        "",
        "![Injection response](injection_response.png)",
    ]
    ANALYSIS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    grouped = read_results()
    save_latency_throughput(grouped)
    save_injection_response(grouped)
    write_summary(grouped)
    print(f"plots and summaries written under {TASK_DIR}")


if __name__ == "__main__":
    main()
