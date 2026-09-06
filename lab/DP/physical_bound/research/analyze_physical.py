#!/usr/bin/env python3
"""Digest the equal-physical DP sweep (results_physical.csv).

Outputs, per family (PA = DOR+CBS vcs=4, PB = adaptive+escape vcs=4):

1. saturation-throughput table: pattern x cap, delta vs the uncapped
   plain mode of the same family (the equal-physical baseline);
2. sanity anchors: PB6 (cap never binds, same alloc order) must be
   bit-identical to PB0; PA4 (cap never binds, shared-first order
   differs) reported either way;
3. latency at matched sub-saturation load: for each pattern, the
   highest rate at which EVERY mode of the family still accepts the
   offered load (injection_acceptance >= 0.99 and delivery keeps up),
   packet latency per mode there;
4. deadlock count (must be 0 everywhere).

Writes summary_physical.csv (per mode x pattern saturation digest).
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent
RESULTS = TASK_DIR / "results_physical.csv"
SUMMARY = TASK_DIR / "summary_physical.csv"

FAMILIES = {
    "PA": {
        "plain": "PA0_cbs_v4",
        "caps": {
            "PA1_dpcbs_v4_s1": 1,
            "PA2_dpcbs_v4_s2": 2,
            "PA3_dpcbs_v4_s3": 3,
            "PA4_dpcbs_v4_s4": 4,
        },
        "pool_physical": 4,
    },
    "PB": {
        "plain": "PB0_esc_v4",
        "caps": {
            "PB1_dpesc_v4_s1": 1,
            "PB2_dpesc_v4_s2": 2,
            "PB3_dpesc_v4_s3": 3,
            "PB4_dpesc_v4_s4": 4,
            "PB5_dpesc_v4_s5": 5,
            "PB6_dpesc_v4_s6": 6,
        },
        "pool_physical": 6,
    },
    "PC": {
        "plain": "PC0_esc_v3",
        "caps": {
            "PC1_dpesc_v3_s1": 1,
            "PC2_dpesc_v3_s2": 2,
            "PC3_dpesc_v3_s3": 3,
            "PC4_dpesc_v3_s4": 4,
        },
        "pool_physical": 4,
    },
}
PATTERNS = [
    "torus3d_xopposite",
    "torus3d_tornado",
    "torus3d_transpose",
    "torus3d_neighbor",
    "uniform_random",
]


def load() -> dict[tuple[str, str], dict[float, dict[str, str]]]:
    table: dict[tuple[str, str], dict[float, dict[str, str]]] = defaultdict(
        dict
    )
    with RESULTS.open(newline="", encoding="utf-8") as csv_file:
        for row in csv.DictReader(csv_file):
            key = (row["mode"], row["pattern"])
            table[key][float(row["injection_rate"])] = row
    return table


def sat_throughput(curve: dict[float, dict[str, str]]) -> tuple[float, float]:
    best_rate, best = 0.0, 0.0
    for rate, row in curve.items():
        thr = float(row["throughput"])
        if thr > best:
            best_rate, best = rate, thr
    return best, best_rate


def identical(
    a: dict[float, dict[str, str]], b: dict[float, dict[str, str]]
) -> bool:
    keys = ("packets_injected", "packets_received", "packet_latency",
            "network_latency", "queueing_latency", "average_hops")
    rates = sorted(set(a) & set(b))
    if not rates or len(rates) != len(a) or len(rates) != len(b):
        return False
    return all(
        all(a[r][k] == b[r][k] for k in keys) for r in rates
    )


def matched_load_rate(
    curves: list[dict[float, dict[str, str]]]
) -> float | None:
    """Highest rate every mode still fully accepts and delivers."""
    common = set.intersection(*(set(c) for c in curves))
    good = [
        rate
        for rate in common
        if all(
            float(c[rate]["injection_acceptance"]) >= 0.99
            and float(c[rate]["delivery_ratio"]) >= 0.95
            for c in curves
        )
    ]
    return max(good) if good else None


def main() -> None:
    table = load()
    deadlocks = sum(
        int(row["deadlock"])
        for curves in table.values()
        for row in curves.values()
    )
    total_rows = sum(len(c) for c in table.values())
    print(f"rows: {total_rows}   deadlocks: {deadlocks}")

    summary_rows: list[dict[str, object]] = []
    for fam_name, fam in FAMILIES.items():
        plain = fam["plain"]
        print(f"\n===== family {fam_name} (plain baseline: {plain}, "
              f"physical pool/pair = {fam['pool_physical']}) =====")
        header = (
            f"{'pattern':<20}{'plain':>8} "
            + "".join(f"{'S=' + str(s):>8}" for s in fam["caps"].values())
        )
        print(header + "   (saturation throughput; delta% vs plain below)")
        for pattern in PATTERNS:
            plain_curve = table.get((plain, pattern), {})
            if not plain_curve:
                continue
            sat_plain, _ = sat_throughput(plain_curve)
            cells, deltas = [], []
            for mode in fam["caps"]:
                curve = table.get((mode, pattern), {})
                if not curve:
                    cells.append(float("nan"))
                    deltas.append(float("nan"))
                    continue
                sat, _ = sat_throughput(curve)
                cells.append(sat)
                deltas.append(
                    (sat - sat_plain) / sat_plain * 100
                    if sat_plain
                    else math.nan
                )
                summary_rows.append(
                    {
                        "family": fam_name,
                        "mode": mode,
                        "cap": fam["caps"][mode],
                        "pattern": pattern,
                        "sat_throughput": f"{sat:.6f}",
                        "sat_plain": f"{sat_plain:.6f}",
                        "delta_pct": f"{deltas[-1]:.2f}",
                    }
                )
            print(
                f"{pattern:<20}{sat_plain:>8.4f} "
                + "".join(f"{c:>8.4f}" for c in cells)
            )
            print(
                f"{'':<20}{'':>8} "
                + "".join(f"{d:>+8.1f}" for d in deltas)
            )

        # sanity anchors
        max_cap_mode = max(fam["caps"], key=lambda m: fam["caps"][m])
        same = all(
            identical(
                table.get((max_cap_mode, p), {}), table.get((plain, p), {})
            )
            for p in PATTERNS
            if (plain, p) in table
        )
        print(
            f"anchor: {max_cap_mode} vs {plain} bit-identical across "
            f"all patterns/rates: {same}"
        )

        # matched-load latency
        print(f"{'pattern':<20}{'rate':>6}{'plain_lat':>10} "
              + "".join(f"{'S=' + str(s):>9}" for s in fam["caps"].values()))
        for pattern in PATTERNS:
            curves = [table.get((plain, pattern), {})] + [
                table.get((m, pattern), {}) for m in fam["caps"]
            ]
            if not all(curves):
                continue
            rate = matched_load_rate(curves)
            if rate is None:
                print(f"{pattern:<20}{'--':>6}")
                continue
            lat_plain = float(table[(plain, pattern)][rate]["packet_latency"])
            lats = [
                float(table[(m, pattern)][rate]["packet_latency"])
                for m in fam["caps"]
            ]
            print(
                f"{pattern:<20}{rate:>6.2f}{lat_plain:>10.1f} "
                + "".join(f"{v:>9.1f}" for v in lats)
            )

    with SUMMARY.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "family", "mode", "cap", "pattern",
                "sat_throughput", "sat_plain", "delta_pct",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"\nsummary written to {SUMMARY}")


if __name__ == "__main__":
    main()
