#!/usr/bin/env python3
"""Equal-PHYSICAL-storage control sweep for the Dimension Pool (DP).

Question: with the physical VC count held fixed, does the DP cap (the
counter) ever produce an advantage over the plain uncapped router?

Every mode below has the SAME hardware: vcs=4 per vnet per inport.
The only variable is the pool cap S (and, at S = max, only the
shared-first allocation order). Any measured difference is therefore a
pure flow-control-policy effect, not a buffer-count effect — this is
the frame the naive-research sweep (equal-usable/commitment) did not
cover.

  PA family: DOR + CBS substrate (routing algorithm 3), vcs=4, r=2.
    Pooled slots: 2 per side, 4 per pair. cap range [1, 4].
    PA0_cbs_v4        plain CBS, uncapped        (= A3 in naive sweep)
    PA1..PA4          DP r=2, cap S = 1..4
    S=4 never binds: isolates the shared-first allocation-order effect
    (DP-CBS scans pooled window [2,4) before dedicated [0,2); plain
    scans [0,4) — so PA4 vs PA0 need not be bit-identical).

  PB family: adaptive + Mesh3D escape (routing algorithm 4), vcs=4,
    escape=1. Pooled slots: 3 per side, 6 per pair. cap range [1, 6].
    PB0_esc_v4        plain escape, uncapped     (= B5 in naive sweep)
    PB1..PB6          DP cap S = 1..6
    S=6 never binds and the allocation order matches plain, so
    PB6 ≡ PB0 is expected bit-identically (sanity anchor).

A gem5 deadlock panic is a result, not an error: recorded deadlock=1.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def find_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "build/NULL/gem5.opt").is_file():
            return candidate
    raise RuntimeError("could not locate the gem5 repository root")


REPO_ROOT = find_repo_root()
GEM5 = REPO_ROOT / "build/NULL/gem5.opt"
CONFIG = REPO_ROOT / "configs/example/garnet_synth_traffic.py"
TASK_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = TASK_DIR / "artifacts_physical"
RUN_DIR = ARTIFACT_DIR / "runs"
LOG_DIR = ARTIFACT_DIR / "logs"
RESULTS = TASK_DIR / "results_physical.csv"

# mode -> (routing algorithm, vcs_per_vnet, extra gem5 flags)
MODE_TABLE: dict[str, tuple[int, int, list[str]]] = {
    "PA0_cbs_v4": (3, 4, ["--enable-cbs"]),
    "PA1_dpcbs_v4_s1": (
        3, 4,
        ["--enable-cbs", "--enable-dp", "--dp-reserve=2",
         "--dp-shared-cap=1"],
    ),
    "PA2_dpcbs_v4_s2": (
        3, 4,
        ["--enable-cbs", "--enable-dp", "--dp-reserve=2",
         "--dp-shared-cap=2"],
    ),
    "PA3_dpcbs_v4_s3": (
        3, 4,
        ["--enable-cbs", "--enable-dp", "--dp-reserve=2",
         "--dp-shared-cap=3"],
    ),
    "PA4_dpcbs_v4_s4": (
        3, 4,
        ["--enable-cbs", "--enable-dp", "--dp-reserve=2",
         "--dp-shared-cap=4"],
    ),
    "PB0_esc_v4": (4, 4, []),
    "PB1_dpesc_v4_s1": (4, 4, ["--enable-dp", "--dp-shared-cap=1"]),
    "PB2_dpesc_v4_s2": (4, 4, ["--enable-dp", "--dp-shared-cap=2"]),
    "PB3_dpesc_v4_s3": (4, 4, ["--enable-dp", "--dp-shared-cap=3"]),
    "PB4_dpesc_v4_s4": (4, 4, ["--enable-dp", "--dp-shared-cap=4"]),
    "PB5_dpesc_v4_s5": (4, 4, ["--enable-dp", "--dp-shared-cap=5"]),
    "PB6_dpesc_v4_s6": (4, 4, ["--enable-dp", "--dp-shared-cap=6"]),
    # PC family: adaptive + escape at vcs=3 — the plain vcs=3 router
    # saturates BELOW the 0.5 injection ceiling on 4/5 patterns, so this
    # family has real headroom for a cap to beat plain (PB's plain sits
    # at the ceiling everywhere, where a win is impossible by
    # construction). Pooled slots: 2 per side, 4 per pair; cap [1, 4].
    "PC0_esc_v3": (4, 3, []),
    "PC1_dpesc_v3_s1": (4, 3, ["--enable-dp", "--dp-shared-cap=1"]),
    "PC2_dpesc_v3_s2": (4, 3, ["--enable-dp", "--dp-shared-cap=2"]),
    "PC3_dpesc_v3_s3": (4, 3, ["--enable-dp", "--dp-shared-cap=3"]),
    "PC4_dpesc_v3_s4": (4, 3, ["--enable-dp", "--dp-shared-cap=4"]),
}
MODES = list(MODE_TABLE)
PATTERNS = [
    "torus3d_xopposite",
    "torus3d_tornado",
    "torus3d_transpose",
    "torus3d_neighbor",
    "uniform_random",
]
DEFAULT_RATES = [i / 20 for i in range(1, 21)]
DEFAULT_SIM_CYCLES = 10000
NODES = 64

STAT_NAMES = {
    "sim_ticks": "simTicks",
    "packets_injected": "system.ruby.network.packets_injected::total",
    "packets_received": "system.ruby.network.packets_received::total",
    "queueing_latency": (
        "system.ruby.network.average_packet_queueing_latency"
    ),
    "network_latency": "system.ruby.network.average_packet_network_latency",
    "packet_latency": "system.ruby.network.average_packet_latency",
    "average_hops": "system.ruby.network.average_hops",
    "cbs_entry_blocks": "system.ruby.network.cbs_entry_blocks",
    "cbs_mark_moves": "system.ruby.network.cbs_mark_moves",
    "dp_pool_blocks": "system.ruby.network.dp_pool_blocks",
    "dp_shared_grants": "system.ruby.network.dp_shared_grants",
    "escape_hops": "system.ruby.network.escape_hops",
    "escape_transitions": "system.ruby.network.escape_transitions",
}

FIELDNAMES = [
    "mode",
    "pattern",
    "injection_rate",
    "vcs_per_vnet",
    "sim_cycles",
    "deadlock",
    "expected_generated",
    "packets_injected",
    "packets_received",
    "injection_acceptance",
    "delivery_ratio",
    "throughput",
    "queueing_latency",
    "network_latency",
    "packet_latency",
    "average_hops",
    "cbs_entry_blocks",
    "cbs_mark_moves",
    "dp_pool_blocks",
    "dp_shared_grants",
    "escape_hops",
    "escape_transitions",
    "sim_ticks",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--modes", nargs="+", choices=MODES, default=MODES)
    parser.add_argument(
        "--patterns", nargs="+", choices=PATTERNS, default=PATTERNS
    )
    parser.add_argument(
        "--rates", nargs="+", type=float, default=DEFAULT_RATES
    )
    parser.add_argument("--sim-cycles", type=int, default=DEFAULT_SIM_CYCLES)
    parser.add_argument("--results", type=Path, default=RESULTS)
    parser.add_argument(
        "--jobs", type=int, default=min(8, os.cpu_count() or 1)
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--keep-runs", action="store_true")
    return parser.parse_args()


def parse_stats(path: Path) -> dict[str, float]:
    wanted = {stat_name: key for key, stat_name in STAT_NAMES.items()}
    values: dict[str, float] = {}
    with path.open(encoding="utf-8") as stats_file:
        for line in stats_file:
            fields = line.split()
            if len(fields) >= 2 and fields[0] in wanted:
                values[wanted[fields[0]]] = float(fields[1])
    return values


def existing_points(
    results_path: Path, force: bool
) -> set[tuple[str, str, str, str]]:
    if force or not results_path.exists():
        return set()
    with results_path.open(newline="", encoding="utf-8") as csv_file:
        return {
            (
                row["mode"],
                row["pattern"],
                f"{float(row['injection_rate']):.2f}",
                row["sim_cycles"],
            )
            for row in csv.DictReader(csv_file)
        }


def run_point(
    mode: str,
    pattern: str,
    rate: float,
    sim_cycles: int,
    keep_runs: bool,
) -> dict[str, float | str]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    routing, vcs, extra = MODE_TABLE[mode]
    rate_text = f"{rate:.2f}"
    name = f"{mode}_{pattern}_{rate_text}_c{sim_cycles}"
    point_run_dir = RUN_DIR / name
    point_run_dir.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{name}.log"
    command = [
        str(GEM5),
        "-d",
        str(point_run_dir),
        str(CONFIG),
        "--network=garnet",
        f"--num-cpus={NODES}",
        f"--num-dirs={NODES}",
        "--topology=Torus3D",
        "--torus-x=4",
        "--torus-y=4",
        "--torus-z=4",
        f"--routing-algorithm={routing}",
        f"--vcs-per-vnet={vcs}",
        "--inj-vnet=0",
        f"--synthetic={pattern}",
        f"--sim-cycles={sim_cycles}",
        f"--injectionrate={rate_text}",
    ] + extra
    with log_path.open("w", encoding="utf-8") as log_file:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            check=False,
        )

    deadlock = 0
    if result.returncode != 0:
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        if "deadlock" in log_text.lower():
            deadlock = 1
        else:
            raise RuntimeError(f"gem5 failed for {name}; see {log_path}")

    stats_path = point_run_dir / "stats.txt"
    stats: dict[str, float] = {}
    if stats_path.is_file():
        stats = parse_stats(stats_path)
    for key in STAT_NAMES:
        stats.setdefault(key, math.nan)

    system_cycles = sim_cycles / 2
    expected = NODES * system_cycles * rate
    injected = stats["packets_injected"]
    received = stats["packets_received"]
    row: dict[str, float | str] = {
        "mode": mode,
        "pattern": pattern,
        "injection_rate": rate,
        "vcs_per_vnet": vcs,
        "sim_cycles": sim_cycles,
        "deadlock": deadlock,
        "expected_generated": expected,
        **stats,
        "injection_acceptance": (
            injected / expected if expected else math.nan
        ),
        "delivery_ratio": received / injected if injected else math.nan,
        "throughput": received / NODES / sim_cycles,
    }
    if not keep_runs:
        shutil.rmtree(point_run_dir, ignore_errors=True)
    return row


def sort_results(results_path: Path) -> None:
    with results_path.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))
    mode_order = {mode: index for index, mode in enumerate(MODES)}
    pattern_order = {pattern: index for index, pattern in enumerate(PATTERNS)}
    rows.sort(
        key=lambda row: (
            pattern_order[row["pattern"]],
            mode_order[row["mode"]],
            int(row["sim_cycles"]),
            float(row["injection_rate"]),
        )
    )
    temporary = results_path.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file, fieldnames=FIELDNAMES, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(results_path)


def main() -> int:
    args = parse_args()
    rates = sorted(set(args.rates))
    if any(rate <= 0 or rate > 1 for rate in rates):
        raise SystemExit("all injection rates must be in the interval (0, 1]")

    all_points = [
        (mode, pattern, rate)
        for pattern in args.patterns
        for mode in args.modes
        for rate in rates
    ]
    results_path = args.results.resolve()
    results_path.parent.mkdir(parents=True, exist_ok=True)
    completed = existing_points(results_path, args.force)
    points = [
        point
        for point in all_points
        if (
            point[0],
            point[1],
            f"{point[2]:.2f}",
            str(args.sim_cycles),
        )
        not in completed
    ]
    file_mode = "w" if args.force or not results_path.exists() else "a"
    print(
        f"{len(all_points) - len(points)} completed point(s), "
        f"{len(points)} remaining; running {args.jobs} concurrent job(s)",
        flush=True,
    )
    with results_path.open(
        file_mode, newline="", encoding="utf-8"
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file, fieldnames=FIELDNAMES, lineterminator="\n"
        )
        if file_mode == "w":
            writer.writeheader()
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {
                executor.submit(
                    run_point,
                    point[0],
                    point[1],
                    point[2],
                    args.sim_cycles,
                    args.keep_runs,
                ): point
                for point in points
            }
            for done, future in enumerate(as_completed(futures), start=1):
                point = futures[future]
                writer.writerow(future.result())
                csv_file.flush()
                print(
                    f"[{done:3d}/{len(points)}] done "
                    f"{point[0]} {point[1]} {point[2]:.2f}",
                    flush=True,
                )
    sort_results(results_path)
    print(f"results written to {results_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
