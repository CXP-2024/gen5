#!/usr/bin/env python3
"""Run the Lab 3 Task 1 Ring and 4x4 Mesh comparison sweep."""

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

TOPOLOGIES = ["ring", "mesh"]
DEFAULT_RATES = [i / 100 for i in range(1, 51)]
SIM_CYCLES = 10000
SYSTEM_CYCLES = SIM_CYCLES // 2
NODES = 16

STAT_NAMES = {
    "sim_ticks": "simTicks",
    "sim_freq": "simFreq",
    "packets_injected": "system.ruby.network.packets_injected::total",
    "packets_received": "system.ruby.network.packets_received::total",
    "flits_injected": "system.ruby.network.flits_injected::total",
    "flits_received": "system.ruby.network.flits_received::total",
    "queueing_latency": "system.ruby.network.average_packet_queueing_latency",
    "network_latency": "system.ruby.network.average_packet_network_latency",
    "packet_latency": "system.ruby.network.average_packet_latency",
    "average_hops": "system.ruby.network.average_hops",
    "average_link_utilization": "system.ruby.network.avg_link_utilization",
}

FIELDNAMES = [
    "topology",
    "injection_rate",
    "offered_load",
    "expected_generated",
    "packets_injected",
    "packets_received",
    "flits_injected",
    "flits_received",
    "injection_acceptance",
    "delivery_ratio",
    "throughput",
    "queueing_latency",
    "network_latency",
    "packet_latency",
    "average_hops",
    "average_link_utilization",
    "sim_ticks",
    "sim_freq",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--topologies", nargs="+", choices=TOPOLOGIES, default=TOPOLOGIES
    )
    parser.add_argument(
        "--rates", nargs="+", type=float, default=DEFAULT_RATES
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=min(8, os.cpu_count() or 1),
        help="number of gem5 simulations to run concurrently (default: 8)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="discard the existing CSV instead of resuming missing points",
    )
    parser.add_argument(
        "--keep-runs",
        action="store_true",
        help="retain full gem5 output directories after successful points",
    )
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
        raise RuntimeError(
            f"missing statistics in {path}: {', '.join(missing)}"
        )
    return values


def existing_points(force: bool) -> set[tuple[str, str]]:
    if force or not RESULTS.exists():
        return set()
    with RESULTS.open(newline="", encoding="utf-8") as csv_file:
        return {
            (row["topology"], f"{float(row['injection_rate']):.2f}")
            for row in csv.DictReader(csv_file)
        }


def run_point(
    topology: str, rate: float, keep_runs: bool
) -> dict[str, float | str]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    rate_text = f"{rate:.2f}"
    name = f"{topology}_{rate_text}"
    point_run_dir = RUN_DIR / name
    point_run_dir.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{name}.log"

    topology_args = (
        ["--topology=Ring", "--routing-algorithm=2"]
        if topology == "ring"
        else [
            "--topology=Mesh_XY",
            "--mesh-rows=4",
            "--routing-algorithm=1",
        ]
    )
    command = [
        str(GEM5),
        "-d",
        str(point_run_dir),
        str(CONFIG),
        "--network=garnet",
        f"--num-cpus={NODES}",
        f"--num-dirs={NODES}",
        "--inj-vnet=0",
        "--synthetic=uniform_random",
        f"--sim-cycles={SIM_CYCLES}",
        f"--injectionrate={rate_text}",
        *topology_args,
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
    expected_generated = NODES * SYSTEM_CYCLES * rate
    injected = stats["packets_injected"]
    received = stats["packets_received"]
    row: dict[str, float | str] = {
        "topology": topology,
        "injection_rate": rate,
        "offered_load": rate / 2,
        "expected_generated": expected_generated,
        **stats,
        "injection_acceptance": injected / expected_generated,
        "delivery_ratio": received / injected if injected else math.nan,
        "throughput": received / NODES / SIM_CYCLES,
    }
    if not keep_runs:
        shutil.rmtree(point_run_dir)
    return row


def sort_results() -> None:
    with RESULTS.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))
    topology_order = {name: index for index, name in enumerate(TOPOLOGIES)}
    rows.sort(
        key=lambda row: (
            topology_order[row["topology"]],
            float(row["injection_rate"]),
        )
    )
    temporary = RESULTS.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file, fieldnames=FIELDNAMES, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(RESULTS)


def main() -> int:
    args = parse_args()
    rates = sorted(set(args.rates))
    if any(rate <= 0 or rate > 1 for rate in rates):
        raise SystemExit("all injection rates must be in the interval (0, 1]")
    if args.jobs < 1:
        raise SystemExit("--jobs must be at least 1")

    completed = existing_points(args.force)
    all_points = [
        (topology, rate) for topology in args.topologies for rate in rates
    ]
    points = [
        point
        for point in all_points
        if (point[0], f"{point[1]:.2f}") not in completed
    ]
    mode = "w" if args.force or not RESULTS.exists() else "a"
    print(
        f"{len(all_points) - len(points)} completed point(s), "
        f"{len(points)} remaining; running {args.jobs} concurrent job(s)",
        flush=True,
    )
    with RESULTS.open(mode, newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file, fieldnames=FIELDNAMES, lineterminator="\n"
        )
        if mode == "w":
            writer.writeheader()
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {
                executor.submit(run_point, topology, rate, args.keep_runs): (
                    topology,
                    rate,
                )
                for topology, rate in points
            }
            for done, future in enumerate(as_completed(futures), start=1):
                topology, rate = futures[future]
                writer.writerow(future.result())
                csv_file.flush()
                print(
                    f"[{done:3d}/{len(points)}] done {topology:4s} {rate:.2f}",
                    flush=True,
                )
    sort_results()
    print(f"results written to {RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
