#!/usr/bin/env python3
"""Plot and summarize the Lab 2 Task 1 sweep."""

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

PATTERNS = ["uniform_random", "shuffle", "transpose", "tornado", "neighbor"]
LABELS = {
    "uniform_random": "Uniform random",
    "shuffle": "Shuffle",
    "transpose": "Transpose",
    "tornado": "Tornado",
    "neighbor": "Neighbor",
}
COLORS = {
    "uniform_random": "#1f77b4",
    "shuffle": "#2ca02c",
    "transpose": "#d62728",
    "tornado": "#9467bd",
    "neighbor": "#ff7f0e",
}
MARKERS = {
    "uniform_random": "o",
    "shuffle": "s",
    "transpose": "^",
    "tornado": "D",
    "neighbor": "v",
}
THEORETICAL_HOPS = {
    "uniform_random": 5.25,
    "shuffle": 4.0,
    "transpose": 5.25,
    "tornado": 3.75,
    "neighbor": 1.75,
}


def read_results() -> dict[str, list[dict[str, float]]]:
    grouped: dict[str, list[dict[str, float]]] = defaultdict(list)
    with RESULTS.open(newline="", encoding="utf-8") as csv_file:
        for raw_row in csv.DictReader(csv_file):
            pattern = raw_row.pop("pattern")
            grouped[pattern].append(
                {key: float(value) for key, value in raw_row.items()}
            )
    for rows in grouped.values():
        rows.sort(key=lambda row: row["injection_rate"])
    missing = [pattern for pattern in PATTERNS if pattern not in grouped]
    if missing:
        raise RuntimeError(f"missing patterns: {', '.join(missing)}")
    return grouped


def style_axis(axis: plt.Axes) -> None:
    axis.grid(True, color="#d8dee4", linewidth=0.7, alpha=0.8)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)


def plot_line(
    axis: plt.Axes,
    rows: list[dict[str, float]],
    pattern: str,
    x_key: str,
    y_key: str,
) -> None:
    axis.plot(
        [row[x_key] for row in rows],
        [row[y_key] for row in rows],
        label=LABELS[pattern],
        color=COLORS[pattern],
        marker=MARKERS[pattern],
        markersize=3.5,
        markevery=3,
        linewidth=1.7,
    )


def save_latency_throughput(
    grouped: dict[str, list[dict[str, float]]]
) -> None:
    figure, axis = plt.subplots(figsize=(7.4, 5.0), constrained_layout=True)
    for pattern in PATTERNS:
        plot_line(
            axis, grouped[pattern], pattern, "throughput", "packet_latency"
        )
    axis.set_xlabel("Achieved throughput (packets/node/Ruby cycle)")
    axis.set_ylabel("Average packet latency (Ruby cycles)")
    axis.set_title("8x8 Mesh: Latency-Throughput Curves")
    axis.legend(frameon=False, ncol=2)
    style_axis(axis)
    for extension in ("png", "pdf"):
        figure.savefig(TASK_DIR / f"latency_throughput.{extension}", dpi=220)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(7.4, 5.0), constrained_layout=True)
    for pattern in PATTERNS:
        plot_line(
            axis, grouped[pattern], pattern, "throughput", "packet_latency"
        )
    axis.set_xlabel("Achieved throughput (packets/node/Ruby cycle)")
    axis.set_ylabel("Average packet latency (Ruby cycles)")
    axis.set_title("8x8 Mesh: Low-Latency Detail")
    axis.set_ylim(0, 35)
    axis.legend(frameon=False, ncol=2)
    style_axis(axis)
    for extension in ("png", "pdf"):
        figure.savefig(
            TASK_DIR / f"latency_throughput_zoom.{extension}", dpi=220
        )
    plt.close(figure)


def save_overview(grouped: dict[str, list[dict[str, float]]]) -> None:
    figure, axes = plt.subplots(
        2, 2, figsize=(10.2, 7.3), constrained_layout=True
    )
    for pattern in PATTERNS:
        rows = grouped[pattern]
        plot_line(
            axes[0, 0], rows, pattern, "injection_rate", "packet_latency"
        )
        plot_line(axes[0, 1], rows, pattern, "injection_rate", "throughput")
        plot_line(
            axes[1, 0], rows, pattern, "injection_rate", "network_latency"
        )
        plot_line(axes[1, 1], rows, pattern, "injection_rate", "average_hops")

    axes[0, 0].set(title="Total latency", ylabel="Ruby cycles")
    axes[0, 1].set(
        title="Achieved throughput", ylabel="packets/node/Ruby cycle"
    )
    axes[1, 0].set(title="Network latency", ylabel="Ruby cycles")
    axes[1, 1].set(title="Average hops", ylabel="hops/flit")
    for axis in axes.flat:
        axis.set_xlabel("Injection rate (packets/node/system cycle)")
        style_axis(axis)
    axes[0, 0].legend(frameon=False, ncol=2, fontsize=8)
    for extension in ("png", "pdf"):
        figure.savefig(TASK_DIR / f"task1_overview.{extension}", dpi=220)
    plt.close(figure)


def first_rate(rows: list[dict[str, float]], predicate) -> float:
    for row in rows:
        if predicate(row):
            return row["injection_rate"]
    return math.nan


def row_at(rows: list[dict[str, float]], rate: float) -> dict[str, float]:
    return min(rows, key=lambda row: abs(row["injection_rate"] - rate))


def write_summary(grouped: dict[str, list[dict[str, float]]]) -> None:
    fields = [
        "pattern",
        "low_load_latency",
        "measured_hops",
        "theoretical_hops",
        "peak_throughput",
        "peak_throughput_injection_rate",
        "efficiency_knee_rate",
        "latency_2x_rate",
    ]
    summary_rows = []
    for pattern in PATTERNS:
        rows = grouped[pattern]
        low = rows[0]
        peak = max(rows, key=lambda row: row["throughput"])
        summary_rows.append(
            {
                "pattern": pattern,
                "low_load_latency": low["packet_latency"],
                "measured_hops": low["average_hops"],
                "theoretical_hops": THEORETICAL_HOPS[pattern],
                "peak_throughput": peak["throughput"],
                "peak_throughput_injection_rate": peak["injection_rate"],
                "efficiency_knee_rate": first_rate(
                    rows,
                    lambda row: row["throughput"] < 0.9 * row["offered_load"],
                ),
                "latency_2x_rate": first_rate(
                    rows,
                    lambda row: row["packet_latency"]
                    >= 2 * low["packet_latency"],
                ),
            }
        )

    with SUMMARY.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file, fieldnames=fields, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    lines = [
        "# Lab 2 Task 1 measured summary",
        "",
        "The efficiency knee is the first injection rate where achieved throughput",
        "falls below 90% of offered network load. The latency knee is the first",
        "rate where total packet latency reaches twice its value at rate 0.01.",
        "",
        "| Pattern | Low-load latency | Hops (measured/theory) | Peak throughput | Peak at rate | 90% knee | 2x latency |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:

        def display(value: float, digits: int = 3) -> str:
            return (
                "not observed" if math.isnan(value) else f"{value:.{digits}f}"
            )

        lines.append(
            "| {pattern} | {latency:.3f} | {measured:.3f}/{theory:.3f} | "
            "{peak:.6f} | {peak_rate:.2f} | {knee} | {latency_knee} |".format(
                pattern=row["pattern"],
                latency=row["low_load_latency"],
                measured=row["measured_hops"],
                theory=row["theoretical_hops"],
                peak=row["peak_throughput"],
                peak_rate=row["peak_throughput_injection_rate"],
                knee=display(row["efficiency_knee_rate"], 2),
                latency_knee=display(row["latency_2x_rate"], 2),
            )
        )
    low_order = sorted(
        PATTERNS,
        key=lambda pattern: grouped[pattern][0]["packet_latency"],
    )
    at_max = {pattern: row_at(grouped[pattern], 0.50) for pattern in PATTERNS}
    transpose_030 = row_at(grouped["transpose"], 0.30)
    shuffle_046 = row_at(grouped["shuffle"], 0.46)
    lines.extend(
        [
            "",
            "## Method",
            "",
            "Each point uses a 64-node 8x8 Mesh_XY network, single-flit control",
            "traffic on vnet 0, and a 10,000-Ruby-cycle measurement window. The",
            "tester runs at 1 GHz and Ruby at 2 GHz. Therefore an injection rate",
            "of 0.50 corresponds to an offered load of 0.25 packets/node/Ruby cycle.",
            "Achieved throughput is received packets / (64 nodes x 10,000 Ruby cycles).",
            "",
            "## Low-load latency and hop count",
            "",
            "At injection rate 0.01, the latency ranking is "
            + " < ".join(
                f"{LABELS[pattern]} ({grouped[pattern][0]['packet_latency']:.2f})"
                for pattern in low_order
            )
            + " Ruby cycles. The ranking follows path length: neighbor is local to an",
            "adjacent node, tornado has short bounded offsets, shuffle averages four",
            "hops, and uniform random and transpose both average about 5.25 hops.",
            "The measurements closely match the exact theoretical hop counts in the",
            "table. At low load, queueing latency is 2 cycles for every pattern, and",
            "the measured total latency is approximately 5 + 2 x average_hops.",
            "",
            "## Throughput and saturation",
            "",
            f"At rate 0.50, uniform random, tornado, and neighbor deliver "
            f"{at_max['uniform_random']['throughput']:.3f}, "
            f"{at_max['tornado']['throughput']:.3f}, and "
            f"{at_max['neighbor']['throughput']:.3f} packets/node/Ruby cycle. "
            "All are close to the offered load of 0.25, so their saturation points",
            "were not reached in the requested sweep. Neighbor remains almost flat",
            "because its one-hop traffic uses network resources very lightly.",
            f"Transpose reaches twice its low-load latency at rate 0.30 "
            f"({transpose_030['packet_latency']:.2f} cycles), then reaches only "
            f"{at_max['transpose']['throughput']:.3f} throughput at rate 0.50. "
            f"Shuffle's sharp latency knee occurs later, near rate 0.46 "
            f"({shuffle_046['packet_latency']:.2f} cycles); its rate-0.50 throughput "
            f"is {at_max['shuffle']['throughput']:.3f}. These permutation patterns",
            "create persistent concentration on particular links, so they saturate",
            "before spatially distributed uniform-random traffic.",
            "",
            "## Latency composition",
            "",
            f"At rate 0.50, transpose spends "
            f"{at_max['transpose']['queueing_latency']:.2f} of "
            f"{at_max['transpose']['packet_latency']:.2f} cycles in queues, while "
            f"shuffle spends {at_max['shuffle']['queueing_latency']:.2f} of "
            f"{at_max['shuffle']['packet_latency']:.2f}. Thus their rapid latency",
            "growth is dominated by contention and waiting, not by a large increase",
            "in the time needed to traverse an uncongested path.",
            "",
            "## Interpreting hop count under overload",
            "",
            "Transpose's reported average hops falls after congestion begins. XY",
            "routing has not shortened the source-destination paths: the statistic",
            "only includes flits that arrive during the finite simulation. Under",
            "heavy congestion, long-path packets are more likely to remain in flight",
            "at the end, biasing the completed-packet average downward.",
            "",
            "![Latency-throughput curves](latency_throughput.png)",
            "",
            "![Low-latency detail](latency_throughput_zoom.png)",
            "",
            "![Task 1 overview](task1_overview.png)",
        ]
    )
    ANALYSIS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    grouped = read_results()
    save_latency_throughput(grouped)
    save_overview(grouped)
    write_summary(grouped)
    print(f"plots and summaries written under {TASK_DIR}")


if __name__ == "__main__":
    main()
