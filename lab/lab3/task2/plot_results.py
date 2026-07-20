#!/usr/bin/env python3
"""Plot and summarize the Lab 3 Task 2 VC/depth comparison."""

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
MODES = ["vc1_depth1", "vc16_depth1", "vc1_depth16_wormhole"]
LABELS = {
    "vc1_depth1": "VC=1, depth=1",
    "vc16_depth1": "VC=16, depth=1",
    "vc1_depth16_wormhole": "VC=1, depth=16 (wormhole)",
}
COLORS = {
    "vc1_depth1": "#d55e00",
    "vc16_depth1": "#0072b2",
    "vc1_depth16_wormhole": "#009e73",
}
MARKERS = {
    "vc1_depth1": "o",
    "vc16_depth1": "s",
    "vc1_depth16_wormhole": "^",
}


def read_results() -> dict[str, list[dict[str, float]]]:
    grouped: dict[str, list[dict[str, float]]] = defaultdict(list)
    with RESULTS.open(newline="", encoding="utf-8") as csv_file:
        for raw in csv.DictReader(csv_file):
            mode = raw.pop("mode")
            grouped[mode].append(
                {key: float(value) for key, value in raw.items()}
            )
    for rows in grouped.values():
        rows.sort(key=lambda row: row["injection_rate"])
    missing = [mode for mode in MODES if mode not in grouped]
    if missing:
        raise RuntimeError(f"missing modes: {', '.join(missing)}")
    return grouped


def style_axis(axis: plt.Axes) -> None:
    axis.grid(True, color="#d8dee4", linewidth=0.7, alpha=0.8)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)


def stable(rows: list[dict[str, float]]) -> list[dict[str, float]]:
    return [row for row in rows if row["injection_acceptance"] >= 0.9]


def save_latency_throughput(
    grouped: dict[str, list[dict[str, float]]]
) -> None:
    figure, axis = plt.subplots(figsize=(7.6, 5.0), constrained_layout=True)
    for mode in MODES:
        rows = stable(grouped[mode])
        axis.plot(
            [row["throughput"] for row in rows],
            [row["packet_latency"] for row in rows],
            label=LABELS[mode],
            color=COLORS[mode],
            marker=MARKERS[mode],
            markersize=3.5,
            markevery=3,
            linewidth=1.7,
        )
        stalled = [
            row for row in grouped[mode] if row["injection_acceptance"] < 0.9
        ]
        if stalled:
            axis.scatter(
                [row["throughput"] for row in stalled],
                [row["packet_latency"] for row in stalled],
                label=f"{LABELS[mode]} stalled",
                color=COLORS[mode],
                marker="x",
                s=55,
                linewidth=2,
            )
    axis.set_xlabel("Achieved throughput (packets/node/Ruby cycle)")
    axis.set_ylabel("Average packet latency (Ruby cycles)")
    axis.set_title("Ring: VC Count vs. Single-VC Depth")
    axis.legend(frameon=False, fontsize=8)
    style_axis(axis)
    for extension in ("png", "pdf"):
        figure.savefig(TASK_DIR / f"latency_throughput.{extension}", dpi=220)
    plt.close(figure)


def save_acceptance(grouped: dict[str, list[dict[str, float]]]) -> None:
    figure, axes = plt.subplots(
        1, 2, figsize=(10.5, 4.2), constrained_layout=True
    )
    for mode in MODES:
        rows = grouped[mode]
        axes[0].plot(
            [row["injection_rate"] for row in rows],
            [row["throughput"] for row in rows],
            label=LABELS[mode],
            color=COLORS[mode],
            marker=MARKERS[mode],
            markersize=3.2,
            markevery=3,
            linewidth=1.6,
        )
        axes[1].plot(
            [row["injection_rate"] for row in rows],
            [row["injection_acceptance"] for row in rows],
            label=LABELS[mode],
            color=COLORS[mode],
            marker=MARKERS[mode],
            markersize=3.2,
            markevery=3,
            linewidth=1.6,
        )
    axes[0].plot(
        [0.01, 0.50],
        [0.005, 0.25],
        "--",
        color="#555555",
        label="Offered load",
    )
    axes[0].set(title="Throughput response", ylabel="packets/node/Ruby cycle")
    axes[1].set(
        title="Source injection acceptance", ylabel="injected / expected"
    )
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
        "mode",
        "low_load_latency",
        "max_stable_throughput",
        "max_stable_rate",
        "first_stalled_rate",
    ]
    output = []
    for mode in MODES:
        rows = grouped[mode]
        peak = max(stable(rows), key=lambda row: row["throughput"])
        output.append(
            {
                "mode": mode,
                "low_load_latency": rows[0]["packet_latency"],
                "max_stable_throughput": peak["throughput"],
                "max_stable_rate": peak["injection_rate"],
                "first_stalled_rate": first_stalled(rows),
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

    lines = [
        "# Lab 3 Task 2 analysis",
        "",
        "The experiment uses the 16-node Ring, uniform-random vnet-0 control",
        "traffic, and a 10,000-Ruby-cycle window. Each point reports both",
        "received throughput and source injection acceptance.",
        "",
        "| Mode | Low-load latency | Max stable throughput | "
        "Max stable rate | "
        "First stalled rate |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in output:
        lines.append(
            f"| {LABELS[row['mode']]} | {row['low_load_latency']:.3f} | "
            f"{row['max_stable_throughput']:.6f} | "
            f"{row['max_stable_rate']:.2f} | "
            f"{fmt(row['first_stalled_rate'])} |"
        )
    lines.extend(
        [
            "",
            "VC=1/depth=1 has one credit slot and one packet ownership "
            "context.",
            "It is the most sensitive to credit round-trip latency and "
            "head-of-line",
            "blocking. VC=16/depth=1 provides the same total 16 slots as "
            "wormhole",
            "but separates them into independent routing and arbitration "
            "contexts.",
            "VC=1/depth=16 keeps one FIFO and one ownership context while "
            "allowing",
            "sixteen outstanding single-flit packets to consume credits.",
            "",
            "The physical link still transmits at most one flit per cycle in "
            "all three",
            "cases. Improvements therefore come from better link utilization "
            "and",
            "hiding credit latency, not from increased physical bandwidth. A "
            "deep single",
            "VC can still suffer head-of-line blocking when its front packet "
            "requests a",
            "busy output, while multiple VCs can select another ready packet.",
            "",
            "At high Ring load, a drop in source acceptance indicates that "
            "packets are",
            "stuck before injection or that a cyclic channel dependency has "
            "formed;",
            "received/injected alone does not expose this condition. The Ring "
            "routing",
            "algorithm remains susceptible to such cyclic dependencies, so "
            "the",
            "wormhole comparison should be interpreted as buffer-utilization "
            "behavior",
            "within the finite simulation window, not as a proof of deadlock "
            "freedom.",
            "",
            "![Latency-throughput comparison](latency_throughput.png)",
            "",
            "![Throughput and source acceptance](injection_response.png)",
        ]
    )
    ANALYSIS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    grouped = read_results()
    save_latency_throughput(grouped)
    save_acceptance(grouped)
    write_summary(grouped)
    print(f"plots and summaries written under {TASK_DIR}")


if __name__ == "__main__":
    main()
