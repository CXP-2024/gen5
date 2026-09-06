#!/usr/bin/env python3
"""Validate and summarize DP-Phys sweep CSV files as Markdown."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path


DIRECTIONS = ("east", "west", "north", "south", "up", "down")


def is_private(row: dict[str, str]) -> bool:
    return row["mode"].startswith("private_v")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--rate",
        type=float,
        help="Only summarize this injection rate; default is the maximum",
    )
    return parser.parse_args()


def number(row: dict[str, str], key: str) -> float:
    try:
        return float(row.get(key, "nan"))
    except ValueError:
        return math.nan


def close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=0.5)


def mean_ci(values: list[float]) -> tuple[float, float]:
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return math.nan, math.nan
    mean = statistics.fmean(finite)
    if len(finite) == 1:
        return mean, 0.0
    ci = 1.96 * statistics.stdev(finite) / math.sqrt(len(finite))
    return mean, ci


def fmt_mean_ci(values: list[float], digits: int = 3) -> str:
    mean, ci = mean_ci(values)
    if not math.isfinite(mean):
        return "n/a"
    if len(values) <= 1:
        return f"{mean:.{digits}f}"
    return f"{mean:.{digits}f} +/- {ci:.{digits}f}"


def validate(rows: list[dict[str, str]]) -> list[str]:
    dp_rows = [row for row in rows if not is_private(row)]
    checks = {
        "deadlock-free runs": sum(
            number(row, "deadlock") != 0 for row in rows
        ),
        "zero Pool read conflicts": sum(
            number(row, "pool_read_conflicts") != 0 for row in dp_rows
        ),
        "allocation conservation": sum(
            not close(
                number(row, "pool_allocations"),
                number(row, "owned_pool_allocations")
                + number(row, "demand_reclaims"),
            )
            for row in dp_rows
            if math.isfinite(number(row, "owned_pool_allocations"))
        ),
        "migration conservation": sum(
            not close(
                number(row, "owner_migrations"),
                number(row, "demand_reclaims")
                + number(row, "release_handoffs"),
            )
            for row in dp_rows
            if math.isfinite(number(row, "demand_reclaims"))
        ),
        "read/return conservation": sum(
            not close(
                number(row, "pool_reads"),
                number(row, "release_handoffs") + number(row, "release_keeps"),
            )
            for row in dp_rows
            if math.isfinite(number(row, "release_keeps"))
        ),
        "directional allocation sum": sum(
            not close(
                number(row, "pool_allocations"),
                sum(
                    number(row, f"pool_allocations_{direction}")
                    for direction in DIRECTIONS
                ),
            )
            for row in dp_rows
            if math.isfinite(number(row, "pool_allocations_east"))
        ),
        "ownership waits do not over-complete": sum(
            number(row, "ownership_wait_completions")
            > number(row, "ownership_wait_starts")
            for row in dp_rows
            if math.isfinite(number(row, "ownership_wait_starts"))
        ),
    }
    lines = ["## Validation", "", "| Check | Result |", "|---|---:|"]
    for name, failures in checks.items():
        result = "PASS" if failures == 0 else f"FAIL ({failures})"
        lines.append(f"| {name} | {result} |")
    return lines


def paired_ratios(
    rows: list[dict[str, str]], key: str
) -> dict[tuple[str, ...], list[float]]:
    baseline = {
        (
            row["pattern"],
            row["link_latency"],
            row["injection_rate"],
            row.get("physical_vcs", "4"),
            row.get("torus_x", "4"),
            row.get("torus_y", "4"),
            row.get("torus_z", "4"),
            row.get("traffic_epoch_cycles", "0"),
            row.get("traffic_x_bias", "0"),
            row.get("traffic_x_hops", "0"),
            row.get("seed", "1"),
        ): number(row, key)
        for row in rows
        if is_private(row)
    }
    ratios: dict[tuple[str, ...], list[float]] = defaultdict(list)
    for row in rows:
        if is_private(row):
            continue
        point = (
            row["pattern"],
            row["link_latency"],
            row["injection_rate"],
            row.get("physical_vcs", "4"),
            row.get("torus_x", "4"),
            row.get("torus_y", "4"),
            row.get("torus_z", "4"),
            row.get("traffic_epoch_cycles", "0"),
            row.get("traffic_x_bias", "0"),
            row.get("traffic_x_hops", "0"),
            row.get("seed", "1"),
        )
        base = baseline.get(point, math.nan)
        value = number(row, key)
        if math.isfinite(base) and base != 0 and math.isfinite(value):
            group = (
                row["pattern"],
                row["link_latency"],
                row["injection_rate"],
                row.get("physical_vcs", "4"),
                row.get("torus_x", "4"),
                row.get("torus_y", "4"),
                row.get("torus_z", "4"),
                row.get("traffic_epoch_cycles", "0"),
                row.get("traffic_x_bias", "0"),
                row.get("traffic_x_hops", "0"),
                row["mode"],
            )
            ratios[group].append(value / base)
    return ratios


def percent(numerator: float, denominator: float) -> float:
    if not math.isfinite(numerator) or denominator <= 0:
        return math.nan
    return 100.0 * numerator / denominator


def summarize(
    rows: list[dict[str, str]], selected_rate: float | None
) -> list[str]:
    if selected_rate is None:
        selected_rate = max(number(row, "injection_rate") for row in rows)
    selected = [
        row
        for row in rows
        if math.isclose(number(row, "injection_rate"), selected_rate)
    ]
    groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in selected:
        groups[
            (
                row["pattern"],
                row["link_latency"],
                row.get("physical_vcs", "4"),
                row.get("torus_x", "4"),
                row.get("torus_y", "4"),
                row.get("torus_z", "4"),
                row.get("traffic_epoch_cycles", "0"),
                row.get("traffic_x_bias", "0"),
                row.get("traffic_x_hops", "0"),
                row["mode"],
            )
        ].append(row)

    throughput_ratios = paired_ratios(rows, "throughput")
    latency_ratios = paired_ratios(rows, "network_latency")
    lines = [
        "",
        f"## Summary at injection rate {selected_rate:g}",
        "",
        "Values are mean +/- approximate 95% CI across seeds. Ratios are "
        "paired against the private baseline with the same physical VC "
        "count and seed.",
        "",
        "| Pattern | Torus | L | VCs | Epoch | X bias | Hops | Mode | "
        "Throughput | vs base | "
        "Network latency | "
        "vs base | Reclaim % | Handoff % | Pool service % | "
        "Wait complete % | Recovery mean/max | Dominant Pool allocation |",
        "|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|"
        "---:|---:|---:|---:|---|",
    ]
    for group in sorted(groups):
        (
            pattern,
            latency,
            physical_vcs,
            torus_x,
            torus_y,
            torus_z,
            epoch,
            bias,
            hops,
            mode,
        ) = group
        group_rows = groups[group]
        ratio_key = (
            pattern,
            latency,
            f"{selected_rate:g}",
            physical_vcs,
            torus_x,
            torus_y,
            torus_z,
            epoch,
            bias,
            hops,
            mode,
        )
        if ratio_key not in throughput_ratios:
            ratio_key = (
                pattern,
                latency,
                group_rows[0]["injection_rate"],
                physical_vcs,
                torus_x,
                torus_y,
                torus_z,
                epoch,
                bias,
                hops,
                mode,
            )
        allocations = [number(row, "pool_allocations") for row in group_rows]
        reads = [number(row, "pool_reads") for row in group_rows]
        reserved = [number(row, "reserved_reads") for row in group_rows]
        reclaim = [
            percent(number(row, "demand_reclaims"), allocation)
            for row, allocation in zip(group_rows, allocations)
        ]
        handoff = [
            percent(number(row, "release_handoffs"), read)
            for row, read in zip(group_rows, reads)
        ]
        service = [
            percent(read, read + res) for read, res in zip(reads, reserved)
        ]
        wait_completion = [
            percent(
                number(row, "ownership_wait_completions"),
                number(row, "ownership_wait_starts"),
            )
            for row in group_rows
        ]
        wait_mean = [
            number(row, "ownership_wait_cycles")
            / number(row, "ownership_wait_completions")
            if number(row, "ownership_wait_completions") > 0
            else math.nan
            for row in group_rows
        ]
        wait_max = [number(row, "ownership_wait_max") for row in group_rows]
        wait_mean_text = fmt_mean_ci(wait_mean, 2)
        recovery_text = (
            "n/a"
            if wait_mean_text == "n/a"
            else f"{wait_mean_text}/{fmt_mean_ci(wait_max, 2)}"
        )
        direction_totals = {
            direction: sum(
                number(row, f"pool_allocations_{direction}")
                for row in group_rows
            )
            for direction in DIRECTIONS
        }
        total_directional = sum(direction_totals.values())
        if total_directional > 0:
            dominant = max(direction_totals, key=direction_totals.get)
            dominant_share = (
                100 * direction_totals[dominant] / total_directional
            )
            dominant_text = f"{dominant} ({dominant_share:.1f}%)"
        else:
            dominant_text = "n/a"
        throughput_ratio = throughput_ratios.get(ratio_key, [])
        latency_ratio = latency_ratios.get(ratio_key, [])
        lines.append(
            "| {} | {}x{}x{} | {} | {} | {} | {} | {} | {} | {} | {} | "
            "{} | {} | {} | {} | {} | {} | {} | {} |".format(
                pattern,
                torus_x,
                torus_y,
                torus_z,
                latency,
                physical_vcs,
                epoch,
                bias,
                hops,
                mode,
                fmt_mean_ci(
                    [number(row, "throughput") for row in group_rows], 4
                ),
                fmt_mean_ci(throughput_ratio, 3),
                fmt_mean_ci(
                    [number(row, "network_latency") for row in group_rows], 2
                ),
                fmt_mean_ci(latency_ratio, 3),
                fmt_mean_ci(reclaim, 2),
                fmt_mean_ci(handoff, 2),
                fmt_mean_ci(service, 2),
                fmt_mean_ci(wait_completion, 2),
                recovery_text,
                dominant_text,
            )
        )
    return lines


def main() -> int:
    args = parse_args()
    with args.results.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))
    if not rows:
        raise SystemExit("results CSV is empty")

    lines = [
        "# DP-Phys sweep summary",
        "",
        f"Input: `{args.results}` ({len(rows)} runs)",
        "",
    ]
    lines.extend(validate(rows))
    lines.extend(summarize(rows, args.rate))
    report = "\n".join(lines) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
