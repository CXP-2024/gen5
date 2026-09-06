#!/usr/bin/env python3
"""Summarize a full or partial DP-Phys sweep."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent
MODE_ORDER = [
    "PRIV",
    "RR-a",
    "STV-a",
    "RR-b",
    "STV-b",
    "PRIV-v3",
    "STV-r1p4",
    "PRIV-v2",
    "STV-r1p2",
]
DIRECTIONS = ["east", "west", "north", "south", "up", "down"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--results", type=Path, default=TASK_DIR / "results_dpphys.csv"
    )
    parser.add_argument(
        "--summary", type=Path, default=TASK_DIR / "summary_dpphys.csv"
    )
    parser.add_argument("--modes", nargs="+", choices=MODE_ORDER)
    parser.add_argument("--link-latencies", nargs="+", type=int)
    return parser.parse_args()


def value(row: dict[str, str], field: str) -> float:
    try:
        return float(row[field])
    except (KeyError, ValueError):
        return math.nan


def saturation(curve: dict[float, dict[str, str]]) -> tuple[float, float]:
    return max(
        ((value(row, "throughput"), rate) for rate, row in curve.items()),
        default=(math.nan, math.nan),
    )


def matched_rate(curves: list[dict[float, dict[str, str]]]) -> float | None:
    if not curves or any(not curve for curve in curves):
        return None
    common = set.intersection(*(set(curve) for curve in curves))
    good = [
        rate
        for rate in common
        if all(
            value(curve[rate], "injection_acceptance") >= 0.99
            and value(curve[rate], "delivery_ratio") >= 0.95
            for curve in curves
        )
    ]
    return max(good) if good else None


def main() -> int:
    args = parse_args()
    with args.results.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))
    if args.modes:
        rows = [row for row in rows if row["mode"] in args.modes]
    if args.link_latencies:
        rows = [
            row
            for row in rows
            if int(row["link_latency"]) in args.link_latencies
        ]
    table: dict[
        tuple[int, str, str], dict[float, dict[str, str]]
    ] = defaultdict(dict)
    for row in rows:
        key = int(row["link_latency"]), row["pattern"], row["mode"]
        table[key][float(row["injection_rate"])] = row

    deadlocks = sum(int(float(row["deadlock"])) for row in rows)
    print(f"rows={len(rows)} deadlocks={deadlocks}")
    summary: list[dict[str, object]] = []
    groups = sorted({(key[0], key[1]) for key in table})
    for latency, pattern in groups:
        present_modes = [
            mode for mode in MODE_ORDER if (latency, pattern, mode) in table
        ]
        curves = [table[(latency, pattern, mode)] for mode in present_modes]
        baseline = next(
            (mode for mode in present_modes if mode.startswith("PRIV")), None
        )
        priv_curve = (
            table.get((latency, pattern, baseline), {}) if baseline else {}
        )
        priv_sat, _ = saturation(priv_curve)
        match = matched_rate(curves)
        print(f"L={latency} {pattern:<20}", end="")
        for mode, curve in zip(present_modes, curves):
            sat, sat_rate = saturation(curve)
            delta = (
                (sat / priv_sat - 1) * 100
                if priv_sat and math.isfinite(priv_sat)
                else math.nan
            )
            sat_row = curve[sat_rate]
            directional = [value(sat_row, f"received_{d}") for d in DIRECTIONS]
            positive = [count for count in directional if count > 0]
            fairness = min(positive) / max(positive) if positive else math.nan
            packet_latency = (
                value(curve[match], "packet_latency")
                if match is not None
                else math.nan
            )
            summary.append(
                {
                    "link_latency": latency,
                    "pattern": pattern,
                    "mode": mode,
                    "sat_throughput": sat,
                    "sat_rate": sat_rate,
                    "delta_vs_priv_pct": delta,
                    "matched_rate": match if match is not None else "",
                    "matched_packet_latency": packet_latency,
                    "direction_fairness_at_sat": fairness,
                    "grants_migrated_at_sat": value(
                        sat_row, "grants_migrated"
                    ),
                    "credits_returned_at_sat": value(
                        sat_row, "credits_returned"
                    ),
                    "pool_full_blocks_at_sat": value(
                        sat_row, "pool_full_blocks"
                    ),
                    "borrowed_peak_at_sat": value(sat_row, "borrowed_peak"),
                    "grant_queue_max_at_sat": value(
                        sat_row, "grant_queue_max"
                    ),
                    "return_conflicts_at_sat": value(
                        sat_row, "return_credit_conflicts"
                    ),
                }
            )
            print(f" {mode}={sat:.4f}({delta:+.1f}%)", end="")
        print(f" matched={match:.2f}" if match is not None else " matched=--")

    fields = (
        list(summary[0]) if summary else ["link_latency", "pattern", "mode"]
    )
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    with args.summary.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(summary)
    print(f"summary: {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
