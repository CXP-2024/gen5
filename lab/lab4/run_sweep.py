#!/usr/bin/env python3
"""Run the Lab 4 3D Mesh/Torus routing comparison."""

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
ARTIFACT_DIR = TASK_DIR / "artifacts"
RUN_DIR = ARTIFACT_DIR / "runs"
LOG_DIR = ARTIFACT_DIR / "logs"
RESULTS = TASK_DIR / "results.csv"

MODES = ["mesh3d_xyz", "torus3d_dor", "torus3d_adaptive_escape"]
PATTERNS = [
    "uniform_random",
    "torus3d_neighbor",
    "torus3d_tornado",
    "torus3d_transpose",
]
DEFAULT_RATES = [i / 50 for i in range(1, 51)]
DEFAULT_SIM_CYCLES = 10000
NODES = 64

STAT_NAMES = {
    "sim_ticks": "simTicks",
    "sim_freq": "simFreq",
    "packets_injected": "system.ruby.network.packets_injected::total",
    "packets_received": "system.ruby.network.packets_received::total",
    "queueing_latency": (
        "system.ruby.network.average_packet_queueing_latency"
    ),
    "network_latency": "system.ruby.network.average_packet_network_latency",
    "packet_latency": "system.ruby.network.average_packet_latency",
    "average_hops": "system.ruby.network.average_hops",
    "average_link_utilization": "system.ruby.network.avg_link_utilization",
    "adaptive_hops": "system.ruby.network.adaptive_hops",
    "escape_hops": "system.ruby.network.escape_hops",
    "escape_transitions": "system.ruby.network.escape_transitions",
}

FIELDNAMES = [
    "mode",
    "pattern",
    "injection_rate",
    "offered_load",
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
    "average_link_utilization",
    "adaptive_hops",
    "escape_hops",
    "escape_transitions",
    "escape_hop_fraction",
    "sim_ticks",
    "sim_freq",
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
    parser.add_argument(
        "--results",
        type=Path,
        default=RESULTS,
        help="CSV output path (default: lab/lab4/results.csv)",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=min(8, os.cpu_count() or 1),
        help="number of concurrent gem5 simulations (default: 8)",
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
    missing = sorted(set(STAT_NAMES) - set(values))
    if missing:
        missing_text = ", ".join(missing)
        raise RuntimeError(f"missing statistics in {path}: {missing_text}")
    return values


def existing_points(
    results_path: Path, force: bool
) -> set[tuple[str, str, str]]:
    if force or not results_path.exists():
        return set()
    with results_path.open(newline="", encoding="utf-8") as csv_file:
        return {
            (
                row["mode"],
                row["pattern"],
                f"{float(row['injection_rate']):.2f}",
            )
            for row in csv.DictReader(csv_file)
        }


def mode_options(mode: str) -> tuple[str, int]:
    if mode == "mesh3d_xyz":
        return "Mesh3D", 5
    if mode == "torus3d_dor":
        return "Torus3D", 3
    return "Torus3D", 4


def run_point(
    mode: str,
    pattern: str,
    rate: float,
    sim_cycles: int,
    keep_runs: bool,
) -> dict[str, float | str]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    rate_text = f"{rate:.2f}"
    name = f"{mode}_{pattern}_{rate_text}"
    point_run_dir = RUN_DIR / name
    point_run_dir.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{name}.log"
    topology, routing = mode_options(mode)
    command = [
        str(GEM5),
        "-d",
        str(point_run_dir),
        str(CONFIG),
        "--network=garnet",
        f"--num-cpus={NODES}",
        f"--num-dirs={NODES}",
        f"--topology={topology}",
        "--torus-x=4",
        "--torus-y=4",
        "--torus-z=4",
        f"--routing-algorithm={routing}",
        "--vcs-per-vnet=4",
        "--inj-vnet=0",
        f"--synthetic={pattern}",
        f"--sim-cycles={sim_cycles}",
        f"--injectionrate={rate_text}",
    ]
    with log_path.open("w", encoding="utf-8") as log_file:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if result.returncode != 0:
        raise RuntimeError(f"gem5 failed for {name}; see {log_path}")

    stats = parse_stats(point_run_dir / "stats.txt")
    system_cycles = sim_cycles / 2
    expected = NODES * system_cycles * rate
    injected = stats["packets_injected"]
    received = stats["packets_received"]
    classified_hops = stats["adaptive_hops"] + stats["escape_hops"]
    row: dict[str, float | str] = {
        "mode": mode,
        "pattern": pattern,
        "injection_rate": rate,
        "offered_load": rate / 2,
        "expected_generated": expected,
        **stats,
        "injection_acceptance": injected / expected,
        "delivery_ratio": received / injected if injected else math.nan,
        "throughput": received / NODES / sim_cycles,
        "escape_hop_fraction": (
            stats["escape_hops"] / classified_hops if classified_hops else 0.0
        ),
    }
    if not keep_runs:
        shutil.rmtree(point_run_dir)
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
    if args.jobs < 1:
        raise SystemExit("--jobs must be at least 1")
    if args.sim_cycles < 1:
        raise SystemExit("--sim-cycles must be at least 1")

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
        if (point[0], point[1], f"{point[2]:.2f}") not in completed
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
