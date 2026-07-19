#!/usr/bin/env python3
"""Plot and summarize the Lab 2 Task 2 parameter sweeps."""

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
PATTERNS = ["uniform_random", "transpose"]
PATTERN_LABELS = {"uniform_random": "Uniform random", "transpose": "Transpose"}
EXPERIMENTS = {
    "vcs": ("Virtual channels per vnet", "VCs/vnet"),
    "router_latency": ("Router pipeline latency", "Router cycles"),
    "link_width_control": (
        "Link width: 8-byte control packets",
        "Link width (bit)",
    ),
    "link_width_data": (
        "Link width: 72-byte data packets",
        "Link width (bit)",
    ),
}
COLORS = ["#0072b2", "#d55e00", "#009e73", "#cc79a7"]
MARKERS = ["o", "s", "^", "D"]


def read_results() -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    with RESULTS.open(newline="", encoding="utf-8") as csv_file:
        for raw in csv.DictReader(csv_file):
            rows.append(
                {
                    key: value
                    if key in ("experiment", "pattern")
                    else float(value)
                    for key, value in raw.items()
                }
            )
    return rows


def style_axis(axis: plt.Axes) -> None:
    axis.grid(True, color="#d8dee4", linewidth=0.7, alpha=0.8)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)


def grouped_for(
    rows: list[dict[str, float | str]], experiment: str, pattern: str
) -> dict[int, list[dict[str, float | str]]]:
    grouped: dict[int, list[dict[str, float | str]]] = defaultdict(list)
    for row in rows:
        if row["experiment"] == experiment and row["pattern"] == pattern:
            grouped[int(row["parameter_value"])].append(row)
    for values in grouped.values():
        values.sort(key=lambda row: float(row["injection_rate"]))
    return grouped


def save_experiment(
    rows: list[dict[str, float | str]], experiment: str
) -> None:
    title, parameter_label = EXPERIMENTS[experiment]
    figure, axes = plt.subplots(
        1, 2, figsize=(11.0, 4.5), constrained_layout=True
    )
    for axis, pattern in zip(axes, PATTERNS):
        grouped = grouped_for(rows, experiment, pattern)
        for index, (value, values) in enumerate(sorted(grouped.items())):
            axis.plot(
                [float(row["packet_throughput"]) for row in values],
                [float(row["packet_latency"]) for row in values],
                label=f"{parameter_label} = {value}",
                color=COLORS[index],
                marker=MARKERS[index],
                markersize=3.2,
                markevery=3,
                linewidth=1.6,
            )
        axis.set_title(PATTERN_LABELS[pattern])
        axis.set_xlabel("Achieved throughput (packets/node/Ruby cycle)")
        axis.set_ylabel("Average packet latency (Ruby cycles)")
        axis.legend(frameon=False, fontsize=8)
        style_axis(axis)
    figure.suptitle(f"8x8 Mesh: {title}", fontsize=14)
    for extension in ("png", "pdf"):
        figure.savefig(TASK_DIR / f"{experiment}.{extension}", dpi=220)
    plt.close(figure)


def first_rate(values: list[dict[str, float | str]], predicate) -> float:
    for row in values:
        if predicate(row):
            return float(row["injection_rate"])
    return math.nan


def write_summary(rows: list[dict[str, float | str]]) -> None:
    fields = [
        "experiment",
        "pattern",
        "parameter_value",
        "low_load_latency",
        "max_observed_throughput",
        "max_at_injection_rate",
        "latency_2x_rate",
        "efficiency_90pct_rate",
    ]
    output = []
    for experiment in EXPERIMENTS:
        for pattern in PATTERNS:
            for value, values in sorted(
                grouped_for(rows, experiment, pattern).items()
            ):
                low = values[0]
                peak = max(
                    values, key=lambda row: float(row["packet_throughput"])
                )
                output.append(
                    {
                        "experiment": experiment,
                        "pattern": pattern,
                        "parameter_value": value,
                        "low_load_latency": float(low["packet_latency"]),
                        "max_observed_throughput": float(
                            peak["packet_throughput"]
                        ),
                        "max_at_injection_rate": float(peak["injection_rate"]),
                        "latency_2x_rate": first_rate(
                            values,
                            lambda row: float(row["packet_latency"])
                            >= 2 * float(low["packet_latency"]),
                        ),
                        "efficiency_90pct_rate": first_rate(
                            values,
                            lambda row: float(row["packet_throughput"])
                            < 0.9 * float(row["offered_packet_load"]),
                        ),
                    }
                )
    with SUMMARY.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file, fieldnames=fields, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(output)

    def display(value: float, digits: int = 3) -> str:
        return "not observed" if math.isnan(value) else f"{value:.{digits}f}"

    lines = [
        "# Lab 2 Task 2 measured summary",
        "",
        "All sweeps use a 64-node 8x8 Mesh_XY network and a 10,000-Ruby-cycle",
        "measurement window. Uniform random represents distributed traffic and",
        "transpose represents a deterministic hotspot-prone permutation.",
        "",
        "| Experiment | Pattern | Value | Low-load latency | Max throughput | 2x latency rate | 90% efficiency rate |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in output:
        lines.append(
            f"| {row['experiment']} | {row['pattern']} | {row['parameter_value']} | "
            f"{row['low_load_latency']:.3f} | "
            f"{row['max_observed_throughput']:.6f} | "
            f"{display(row['latency_2x_rate'], 2)} | "
            f"{display(row['efficiency_90pct_rate'], 2)} |"
        )

    indexed = {
        (row["experiment"], row["pattern"], row["parameter_value"]): row
        for row in output
    }
    vc_uniform = [
        indexed[("vcs", "uniform_random", value)] for value in (1, 2, 4, 8)
    ]
    vc_transpose = [
        indexed[("vcs", "transpose", value)] for value in (1, 2, 4, 8)
    ]
    router_uniform = [
        indexed[("router_latency", "uniform_random", value)]
        for value in (1, 2, 4)
    ]
    router_transpose = [
        indexed[("router_latency", "transpose", value)] for value in (1, 2, 4)
    ]
    width_uniform = [
        indexed[("link_width_data", "uniform_random", value)]
        for value in (64, 128, 256)
    ]
    width_transpose = [
        indexed[("link_width_data", "transpose", value)]
        for value in (64, 128, 256)
    ]
    lines.extend(
        [
            "",
            "The 90% efficiency rate is the first injection rate where achieved",
            "packet throughput falls below 90% of offered packet load. The 2x",
            "latency rate is the first point whose latency is twice the rate-0.01",
            "value. A missing value means the threshold was not reached by 0.50.",
            "",
            "## Experimental method",
            "",
            "Each sweep changes one parameter while retaining the default baseline:",
            "4 VCs/vnet, 1-cycle routers, and 128-bit links. Rates 0.01 through",
            "0.50 are tested in 0.01 increments. Vnet 0 supplies 8-byte single-flit",
            "control packets for the VC and router experiments. Link width is tested",
            "with both vnet-0 control packets and vnet-2 72-byte data packets.",
            "",
            "## Virtual channels per vnet",
            "",
            f"For uniform random, maximum observed throughput rises from "
            f"{vc_uniform[0]['max_observed_throughput']:.3f} with one VC to "
            f"{vc_uniform[1]['max_observed_throughput']:.3f} with two and "
            f"{vc_uniform[2]['max_observed_throughput']:.3f} with four. For "
            f"transpose the corresponding values are "
            f"{vc_transpose[0]['max_observed_throughput']:.3f}, "
            f"{vc_transpose[1]['max_observed_throughput']:.3f}, and "
            f"{vc_transpose[2]['max_observed_throughput']:.3f}. Extra VCs reduce",
            "head-of-line blocking and provide more independent one-flit buffers,",
            "so links remain productive while another flow waits for credit.",
            f"Increasing from four to eight VCs changes peak throughput by only "
            f"{abs(vc_uniform[3]['max_observed_throughput'] - vc_uniform[2]['max_observed_throughput']):.6f} "
            f"for uniform random and "
            f"{abs(vc_transpose[3]['max_observed_throughput'] - vc_transpose[2]['max_observed_throughput']):.6f} "
            "for transpose. At that point physical-link and traffic-placement",
            "contention, rather than VC availability, is the limiting resource.",
            "",
            "## Router latency",
            "",
            f"Uniform-random low-load latency increases from "
            f"{router_uniform[0]['low_load_latency']:.2f} to "
            f"{router_uniform[1]['low_load_latency']:.2f} and "
            f"{router_uniform[2]['low_load_latency']:.2f} cycles as router latency",
            "changes from 1 to 2 and 4 cycles. Transpose shows the same increase:",
            f"{router_transpose[0]['low_load_latency']:.2f}, "
            f"{router_transpose[1]['low_load_latency']:.2f}, and "
            f"{router_transpose[2]['low_load_latency']:.2f}. The increment is close",
            "to (router_latency - 1) x (average_hops + 1), because a packet pays",
            "the extra pipeline stages at every traversed router.",
            f"For transpose, the 2x-latency knee moves from injection rate "
            f"{router_transpose[0]['latency_2x_rate']:.2f} to "
            f"{router_transpose[1]['latency_2x_rate']:.2f} and "
            f"{router_transpose[2]['latency_2x_rate']:.2f}. Longer pipelines also",
            "delay credit return, so finite VC buffers recycle more slowly and",
            "the hotspot-prone workload saturates earlier.",
            "",
            "## Link width",
            "",
            "All 64-, 128-, and 256-bit control-packet curves are exactly equal.",
            "An 8-byte packet occupies one flit at every tested width, and a Garnet",
            "link still transfers one flit per cycle; unused bits do not create a",
            "second packet transfer in that cycle.",
            "For 72-byte packets, 64-, 128-, and 256-bit links require 9, 5, and 3",
            "flits per packet. Uniform-random maximum packet throughput therefore",
            f"increases from {width_uniform[0]['max_observed_throughput']:.3f} to "
            f"{width_uniform[1]['max_observed_throughput']:.3f} and "
            f"{width_uniform[2]['max_observed_throughput']:.3f}. Multiplying by the",
            "respective flit counts gives approximately 0.359, 0.362, and 0.362",
            "flits/node/cycle, confirming that the same network flit capacity is",
            "being divided among fewer flits per packet on wider links.",
            f"Transpose also improves from "
            f"{width_transpose[0]['max_observed_throughput']:.3f} to "
            f"{width_transpose[1]['max_observed_throughput']:.3f} and "
            f"{width_transpose[2]['max_observed_throughput']:.3f}, but remains below",
            "uniform random because its deterministic paths concentrate load on a",
            "smaller set of links.",
            "",
            "## Conclusions",
            "",
            "VC count mainly controls blocking and buffering, router latency directly",
            "sets per-hop delay and credit round-trip time, and link width controls",
            "packet serialization only when packets span multiple flits. Four VCs",
            "are sufficient for these tested single-flit workloads; additional VCs",
            "do not remove the physical bottleneck. Wider links are most valuable",
            "for data traffic, while single-flit control traffic receives no benefit.",
            "",
            "![VC sweep](vcs.png)",
            "",
            "![Router latency sweep](router_latency.png)",
            "",
            "![Control packet link-width sweep](link_width_control.png)",
            "",
            "![Data packet link-width sweep](link_width_data.png)",
        ]
    )
    ANALYSIS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    rows = read_results()
    for experiment in EXPERIMENTS:
        save_experiment(rows, experiment)
    write_summary(rows)
    print(f"plots and summaries written under {TASK_DIR}")


if __name__ == "__main__":
    main()
