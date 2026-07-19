#!/usr/bin/env python3
"""Run the controlled-parameter sweeps for Lab 2 Task 2."""

from __future__ import annotations

import argparse
import csv
import math
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
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

PATTERNS = ["uniform_random", "transpose"]
DEFAULT_RATES = [i / 100 for i in range(1, 51)]
EXPERIMENTS = [
    "vcs",
    "router_latency",
    "link_width_control",
    "link_width_data",
]

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
    "flit_queueing_latency": "system.ruby.network.average_flit_queueing_latency",
    "flit_network_latency": "system.ruby.network.average_flit_network_latency",
    "flit_latency": "system.ruby.network.average_flit_latency",
    "average_hops": "system.ruby.network.average_hops",
    "average_link_utilization": "system.ruby.network.avg_link_utilization",
}

FIELDNAMES = [
    "experiment",
    "pattern",
    "parameter_value",
    "injection_rate",
    "offered_packet_load",
    "offered_flit_load",
    "inj_vnet",
    "packet_size_bytes",
    "flits_per_packet",
    "vcs_per_vnet",
    "router_latency",
    "link_width_bits",
    "packets_injected",
    "packets_received",
    "flits_injected",
    "flits_received",
    "packet_throughput",
    "flit_throughput",
    "delivery_ratio",
    "queueing_latency",
    "network_latency",
    "packet_latency",
    "flit_queueing_latency",
    "flit_network_latency",
    "flit_latency",
    "average_hops",
    "average_link_utilization",
    "sim_ticks",
    "sim_freq",
]


@dataclass(frozen=True)
class Point:
    experiment: str
    pattern: str
    rate: float
    inj_vnet: int
    vcs_per_vnet: int
    router_latency: int
    link_width_bits: int

    @property
    def parameter_value(self) -> int:
        if self.experiment == "vcs":
            return self.vcs_per_vnet
        if self.experiment == "router_latency":
            return self.router_latency
        return self.link_width_bits

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (
            self.experiment,
            self.pattern,
            str(self.parameter_value),
            f"{self.rate:.2f}",
        )

    @property
    def name(self) -> str:
        return (
            f"{self.experiment}_{self.pattern}_{self.parameter_value}_"
            f"{self.rate:.2f}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--experiments", nargs="+", choices=EXPERIMENTS, default=EXPERIMENTS
    )
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
    parser.add_argument(
        "--keep-runs",
        action="store_true",
        help="retain full gem5 output directories after successful points",
    )
    return parser.parse_args()


def build_points(
    experiments: list[str], patterns: list[str], rates: list[float]
) -> list[Point]:
    points: list[Point] = []
    for experiment in experiments:
        if experiment == "vcs":
            variants = [(0, vcs, 1, 128) for vcs in (1, 2, 4, 8)]
        elif experiment == "router_latency":
            variants = [(0, 4, latency, 128) for latency in (1, 2, 4)]
        elif experiment == "link_width_control":
            variants = [(0, 4, 1, width) for width in (64, 128, 256)]
        else:
            variants = [(2, 4, 1, width) for width in (64, 128, 256)]
        for pattern in patterns:
            for inj_vnet, vcs, latency, width in variants:
                for rate in rates:
                    points.append(
                        Point(
                            experiment,
                            pattern,
                            rate,
                            inj_vnet,
                            vcs,
                            latency,
                            width,
                        )
                    )
    return points


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


def existing_points(force: bool) -> set[tuple[str, str, str, str]]:
    if force or not RESULTS.exists():
        return set()
    with RESULTS.open(newline="", encoding="utf-8") as csv_file:
        return {
            (
                row["experiment"],
                row["pattern"],
                str(int(float(row["parameter_value"]))),
                f"{float(row['injection_rate']):.2f}",
            )
            for row in csv.DictReader(csv_file)
        }


def run_point(point: Point, keep_runs: bool) -> dict[str, float | int | str]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    point_run_dir = RUN_DIR / point.name
    point_run_dir.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{point.name}.log"
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
        f"--inj-vnet={point.inj_vnet}",
        f"--synthetic={point.pattern}",
        "--sim-cycles=10000",
        f"--injectionrate={point.rate:.2f}",
        f"--vcs-per-vnet={point.vcs_per_vnet}",
        f"--router-latency={point.router_latency}",
        f"--link-width-bits={point.link_width_bits}",
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
        raise RuntimeError(f"gem5 failed for {point.name}; see {log_path}")

    stats = parse_stats(point_run_dir / "stats.txt")
    packet_size = 8 if point.inj_vnet == 0 else 72
    flits_per_packet = math.ceil(packet_size * 8 / point.link_width_bits)
    ruby_cycles = 10000
    nodes = 64
    received_packets = stats["packets_received"]
    injected_packets = stats["packets_injected"]
    row: dict[str, float | int | str] = {
        "experiment": point.experiment,
        "pattern": point.pattern,
        "parameter_value": point.parameter_value,
        "injection_rate": point.rate,
        "offered_packet_load": point.rate / 2,
        "offered_flit_load": point.rate / 2 * flits_per_packet,
        "inj_vnet": point.inj_vnet,
        "packet_size_bytes": packet_size,
        "flits_per_packet": flits_per_packet,
        "vcs_per_vnet": point.vcs_per_vnet,
        "router_latency": point.router_latency,
        "link_width_bits": point.link_width_bits,
        **stats,
        "packet_throughput": received_packets / nodes / ruby_cycles,
        "flit_throughput": stats["flits_received"] / nodes / ruby_cycles,
        "delivery_ratio": (
            received_packets / injected_packets
            if injected_packets
            else math.nan
        ),
    }
    if not keep_runs:
        shutil.rmtree(point_run_dir)
    return row


def sort_results() -> None:
    with RESULTS.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))
    order = {name: index for index, name in enumerate(EXPERIMENTS)}
    pattern_order = {name: index for index, name in enumerate(PATTERNS)}
    rows.sort(
        key=lambda row: (
            order[row["experiment"]],
            pattern_order[row["pattern"]],
            float(row["parameter_value"]),
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

    all_points = build_points(args.experiments, args.patterns, rates)
    completed = existing_points(args.force)
    points = [point for point in all_points if point.key not in completed]
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
                executor.submit(run_point, point, args.keep_runs): point
                for point in points
            }
            for done, future in enumerate(as_completed(futures), start=1):
                point = futures[future]
                writer.writerow(future.result())
                csv_file.flush()
                print(
                    f"[{done:4d}/{len(points)}] done {point.name}",
                    flush=True,
                )
    sort_results()
    print(f"results written to {RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
