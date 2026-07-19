#!/usr/bin/env python3
"""Run the Lab 2 Task 1 Garnet traffic-pattern sweep."""

from __future__ import annotations

import argparse
import csv
import math
import os
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

PATTERNS = ["uniform_random", "shuffle", "transpose", "tornado", "neighbor"]
DEFAULT_RATES = [i / 100 for i in range(1, 51)]

STAT_NAMES = {
    "sim_ticks": "simTicks",
    "sim_freq": "simFreq",
    "packets_injected": "system.ruby.network.packets_injected::total",
    "packets_received": "system.ruby.network.packets_received::total",
    "queueing_latency": "system.ruby.network.average_packet_queueing_latency",
    "network_latency": "system.ruby.network.average_packet_network_latency",
    "packet_latency": "system.ruby.network.average_packet_latency",
    "average_hops": "system.ruby.network.average_hops",
}

FIELDNAMES = [
    "pattern",
    "injection_rate",
    "offered_load",
    "packets_injected",
    "packets_received",
    "throughput",
    "delivery_ratio",
    "queueing_latency",
    "network_latency",
    "packet_latency",
    "average_hops",
    "sim_ticks",
    "sim_freq",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--patterns", nargs="+", choices=PATTERNS, default=PATTERNS
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
            (row["pattern"], f"{float(row['injection_rate']):.2f}")
            for row in csv.DictReader(csv_file)
        }


def sort_results() -> None:
    """Keep the versioned CSV deterministic after concurrent runs."""
    with RESULTS.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))
    pattern_order = {pattern: index for index, pattern in enumerate(PATTERNS)}
    rows.sort(
        key=lambda row: (
            pattern_order[row["pattern"]],
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


def run_point(pattern: str, rate: float) -> dict[str, float | str]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    rate_text = f"{rate:.2f}"
    point_run_dir = RUN_DIR / f"{pattern}_{rate_text}"
    point_run_dir.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{pattern}_{rate_text}.log"
    command = [
        str(GEM5),
        "-d",
        str(point_run_dir),
        str(CONFIG),
        "--network=garnet",
        "--num-cpus=64",
        "--num-dirs=64",
        "--topology=Mesh_XY",
        "--mesh-rows=8",
        "--inj-vnet=0",
        f"--synthetic={pattern}",
        "--sim-cycles=10000",
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
        raise RuntimeError(
            f"gem5 failed for {pattern} at {rate_text}; see {log_path}"
        )

    stats = parse_stats(point_run_dir / "stats.txt")
    received = stats["packets_received"]
    injected = stats["packets_injected"]
    sim_cycles = 10000
    nodes = 64
    row: dict[str, float | str] = {
        "pattern": pattern,
        "injection_rate": rate,
        # The tester is 1 GHz and Ruby is 2 GHz.
        "offered_load": rate / 2,
        **stats,
        "throughput": received / nodes / sim_cycles,
        "delivery_ratio": received / injected if injected else math.nan,
    }
    return row


def main() -> int:
    args = parse_args()
    if not GEM5.is_file():
        raise SystemExit(f"gem5 binary not found: {GEM5}")

    rates = sorted(set(args.rates))
    if any(rate <= 0 or rate > 1 for rate in rates):
        raise SystemExit("all injection rates must be in the interval (0, 1]")
    if args.jobs < 1:
        raise SystemExit("--jobs must be at least 1")

    completed = existing_points(args.force)
    mode = "w" if args.force or not RESULTS.exists() else "a"
    total = len(args.patterns) * len(rates)
    points = [
        (pattern, rate)
        for pattern in args.patterns
        for rate in rates
        if (pattern, f"{rate:.2f}") not in completed
    ]
    skipped = total - len(points)
    print(
        f"{skipped} completed point(s), {len(points)} remaining; "
        f"running {args.jobs} concurrent job(s)",
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
                executor.submit(run_point, pattern, rate): (pattern, rate)
                for pattern, rate in points
            }
            for done, future in enumerate(
                as_completed(futures), start=skipped + 1
            ):
                pattern, rate = futures[future]
                writer.writerow(future.result())
                csv_file.flush()
                print(
                    f"[{done:3d}/{total}] done {pattern:14s} {rate:.2f}",
                    flush=True,
                )
    sort_results()
    print(f"results written to {RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
