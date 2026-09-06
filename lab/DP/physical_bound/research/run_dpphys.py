#!/usr/bin/env python3
"""Run the preregistered DP-Phys experiment sweep.

Default: 5 modes x 2 link latencies x 5 patterns x 20 rates = 1000 runs.
Rows are flushed as points finish, so rerunning the same command resumes it.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path


def find_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "build/NULL/gem5.opt").is_file():
            return candidate
    raise RuntimeError("could not locate build/NULL/gem5.opt")


REPO_ROOT = find_repo_root()
GEM5 = REPO_ROOT / "build/NULL/gem5.opt"
CONFIG = REPO_ROOT / "configs/example/garnet_synth_traffic.py"
TASK_DIR = Path(__file__).resolve().parent
NODES = 64


@dataclass(frozen=True)
class Mode:
    vcs: int
    policy: str | None = None
    reserve: int | None = None
    pool: int = 0


# Every row has eight physical slots per dimension pair.  PRIV exposes four
# private slots on each side; pair-global modes use 2*r + P == 8.
MODES = {
    "PRIV": Mode(vcs=4),
    "RR-a": Mode(vcs=8, policy="rr", reserve=2, pool=4),
    "STV-a": Mode(vcs=8, policy="starve", reserve=2, pool=4),
    "RR-b": Mode(vcs=8, policy="rr", reserve=1, pool=6),
    "STV-b": Mode(vcs=8, policy="starve", reserve=1, pool=6),
}
PATTERNS = [
    "torus3d_xopposite",
    "torus3d_tornado",
    "torus3d_transpose",
    "torus3d_neighbor",
    "uniform_random",
]
DIRECTIONS = ["east", "west", "north", "south", "up", "down"]
DEFAULT_RATES = [i / 20 for i in range(1, 21)]

SCALAR_STATS = {
    "sim_ticks": "simTicks",
    "packets_injected": "system.ruby.network.packets_injected::total",
    "packets_received": "system.ruby.network.packets_received::total",
    "queueing_latency": "system.ruby.network.average_packet_queueing_latency",
    "network_latency": "system.ruby.network.average_packet_network_latency",
    "packet_latency": "system.ruby.network.average_packet_latency",
    "average_hops": "system.ruby.network.average_hops",
    "escape_hops": "system.ruby.network.escape_hops",
    "escape_transitions": "system.ruby.network.escape_transitions",
    "grants_migrated": "system.ruby.network.dpphys_grants_migrated",
    "credits_returned": "system.ruby.network.dpphys_credits_returned",
    "pool_full_blocks": "system.ruby.network.dpphys_pool_full_blocks",
    "borrowed_peak": "system.ruby.network.dpphys_borrowed_peak",
    "grant_queue_mean": ("system.ruby.network.dpphys_grant_queue_depth::mean"),
    "grant_queue_max": (
        "system.ruby.network.dpphys_grant_queue_depth::max_value"
    ),
    "return_credit_conflicts": (
        "system.ruby.network.dpphys_return_credit_conflicts"
    ),
}
FIELDNAMES = [
    "mode",
    "policy",
    "reserve",
    "pool_slots",
    "pair_slots",
    "pattern",
    "link_latency",
    "injection_rate",
    "vcs_per_vnet",
    "sim_cycles",
    "random_seed",
    "deadlock",
    "exit_code",
    "wall_seconds",
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
    "escape_hops",
    "escape_transitions",
    "grants_migrated",
    "credits_returned",
    "pool_full_blocks",
    "borrowed_peak",
    "grant_queue_mean",
    "grant_queue_max",
    "return_credit_conflicts",
    *[f"received_{direction}" for direction in DIRECTIONS],
    "received_dir_total",
    "sim_ticks",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--modes", nargs="+", choices=MODES, default=list(MODES)
    )
    parser.add_argument(
        "--patterns", nargs="+", choices=PATTERNS, default=PATTERNS
    )
    parser.add_argument(
        "--link-latencies", nargs="+", type=int, default=[1, 8]
    )
    parser.add_argument(
        "--rates", nargs="+", type=float, default=DEFAULT_RATES
    )
    parser.add_argument("--sim-cycles", type=int, default=10000)
    parser.add_argument("--random-seed", type=int, default=1)
    parser.add_argument("--return-base", type=float, default=0.25)
    parser.add_argument("--return-t1", default="2.0")
    parser.add_argument(
        "--results", type=Path, default=TASK_DIR / "results_dpphys.csv"
    )
    parser.add_argument(
        "--artifact-dir", type=Path, default=TASK_DIR / "artifacts_dpphys"
    )
    parser.add_argument(
        "--jobs", type=int, default=min(8, os.cpu_count() or 1)
    )
    parser.add_argument("--max-points", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--keep-runs", action="store_true")
    return parser.parse_args()


def parse_stats(path: Path) -> dict[str, float]:
    wanted = {stat_name: key for key, stat_name in SCALAR_STATS.items()}
    values: dict[str, float] = {}
    direction_stat = "system.ruby.network.dpphys_received_by_dir "
    with path.open(encoding="utf-8") as stats_file:
        for line in stats_file:
            fields = line.split()
            if len(fields) >= 2 and fields[0] in wanted:
                try:
                    values[wanted[fields[0]]] = float(fields[1])
                except ValueError:
                    pass
            elif line.startswith(direction_stat) and "|" in line:
                for direction, bucket in zip(DIRECTIONS, line.split("|")[1:7]):
                    try:
                        values[f"received_{direction}"] = float(
                            bucket.strip().split()[0]
                        )
                    except (IndexError, ValueError):
                        pass
    for key in SCALAR_STATS:
        values.setdefault(key, math.nan)
    for direction in DIRECTIONS:
        values.setdefault(f"received_{direction}", math.nan)
    direction_values = [
        values[f"received_{direction}"]
        for direction in DIRECTIONS
        if math.isfinite(values[f"received_{direction}"])
    ]
    values["received_dir_total"] = (
        sum(direction_values) if direction_values else math.nan
    )
    return values


def point_key(
    mode: str, pattern: str, latency: int, rate: float, cycles: int, seed: int
) -> tuple[str, str, str, str, str, str]:
    return mode, pattern, str(latency), f"{rate:.2f}", str(cycles), str(seed)


def completed_points(path: Path, force: bool) -> set[tuple[str, ...]]:
    if force or not path.is_file():
        return set()
    with path.open(newline="", encoding="utf-8") as csv_file:
        return {
            point_key(
                row["mode"],
                row["pattern"],
                int(row["link_latency"]),
                float(row["injection_rate"]),
                int(row["sim_cycles"]),
                int(row["random_seed"]),
            )
            for row in csv.DictReader(csv_file)
        }


def gem5_command(
    mode_name: str,
    pattern: str,
    latency: int,
    rate: float,
    args: argparse.Namespace,
    run_dir: Path,
) -> list[str]:
    mode = MODES[mode_name]
    command = [
        str(GEM5),
        "-d",
        str(run_dir),
        str(CONFIG),
        "--network=garnet",
        f"--num-cpus={NODES}",
        f"--num-dirs={NODES}",
        "--topology=Torus3D",
        "--torus-x=4",
        "--torus-y=4",
        "--torus-z=4",
        "--routing-algorithm=4",
        f"--vcs-per-vnet={mode.vcs}",
        "--escape-vcs=1",
        "--inj-vnet=0",
        f"--synthetic={pattern}",
        f"--injectionrate={rate:.2f}",
        f"--sim-cycles={args.sim_cycles}",
        f"--random-seed={args.random_seed}",
        f"--link-latency={latency}",
    ]
    if mode.policy:
        command.extend(
            [
                f"--dpphys-policy={mode.policy}",
                f"--dpphys-r={mode.reserve}",
                f"--dpphys-cap={mode.pool}",
                f"--dpphys-return-base={args.return_base}",
                f"--dpphys-return-t1={args.return_t1}",
            ]
        )
    return command


def run_point(
    point: tuple[str, str, int, float],
    args: argparse.Namespace,
    run_root: Path,
    log_root: Path,
) -> dict[str, object]:
    mode_name, pattern, latency, rate = point
    mode = MODES[mode_name]
    name = (
        f"{mode_name}_{pattern}_L{latency}_r{rate:.2f}_"
        f"c{args.sim_cycles}_s{args.random_seed}"
    )
    run_dir = run_root / name
    log_path = log_root / f"{name}.log"
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log_file:
        result = subprocess.run(
            gem5_command(mode_name, pattern, latency, rate, args, run_dir),
            cwd=REPO_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            check=False,
        )
    elapsed = time.monotonic() - started
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    deadlock = int(result.returncode != 0 and "deadlock" in log_text.lower())
    if result.returncode != 0:
        kind = "deadlock" if deadlock else f"exit {result.returncode}"
        raise RuntimeError(f"{kind} at {name}; see {log_path}")

    stats_path = run_dir / "stats.txt"
    if not stats_path.is_file():
        raise RuntimeError(f"missing stats for {name}; see {log_path}")
    stats = parse_stats(stats_path)
    expected = NODES * (args.sim_cycles / 2) * rate
    injected = stats["packets_injected"]
    received = stats["packets_received"]
    row: dict[str, object] = {
        "mode": mode_name,
        "policy": mode.policy or "private",
        "reserve": mode.reserve if mode.reserve is not None else "",
        "pool_slots": mode.pool,
        "pair_slots": 8,
        "pattern": pattern,
        "link_latency": latency,
        "injection_rate": rate,
        "vcs_per_vnet": mode.vcs,
        "sim_cycles": args.sim_cycles,
        "random_seed": args.random_seed,
        "deadlock": deadlock,
        "exit_code": result.returncode,
        "wall_seconds": f"{elapsed:.3f}",
        "expected_generated": expected,
        **stats,
        "injection_acceptance": injected / expected if expected else math.nan,
        "delivery_ratio": received / injected if injected else math.nan,
        "throughput": received / NODES / args.sim_cycles,
    }
    if not args.keep_runs:
        shutil.rmtree(run_dir, ignore_errors=True)
    return row


def sort_results(path: Path) -> None:
    with path.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))
    mode_order = {mode: index for index, mode in enumerate(MODES)}
    pattern_order = {pattern: index for index, pattern in enumerate(PATTERNS)}
    rows.sort(
        key=lambda row: (
            int(row["link_latency"]),
            pattern_order[row["pattern"]],
            mode_order[row["mode"]],
            float(row["injection_rate"]),
        )
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    rates = sorted(set(args.rates))
    latencies = sorted(set(args.link_latencies))
    if args.jobs < 1 or args.sim_cycles < 1:
        raise SystemExit("--jobs and --sim-cycles must be positive")
    if any(rate <= 0 or rate > 1 for rate in rates):
        raise SystemExit("rates must be in (0, 1]")
    if any(latency < 1 for latency in latencies):
        raise SystemExit("link latencies must be positive")

    all_points = [
        (mode, pattern, latency, rate)
        for latency in latencies
        for pattern in args.patterns
        for mode in args.modes
        for rate in rates
    ]
    if args.max_points is not None:
        all_points = all_points[: args.max_points]
    results = args.results.resolve()
    artifacts = args.artifact_dir.resolve()
    run_root, log_root = artifacts / "runs", artifacts / "logs"
    run_root.mkdir(parents=True, exist_ok=True)
    log_root.mkdir(parents=True, exist_ok=True)
    results.parent.mkdir(parents=True, exist_ok=True)
    completed = completed_points(results, args.force)
    points = [
        point
        for point in all_points
        if point_key(
            point[0],
            point[1],
            point[2],
            point[3],
            args.sim_cycles,
            args.random_seed,
        )
        not in completed
    ]
    file_mode = "w" if args.force or not results.exists() else "a"
    print(
        f"matrix={len(all_points)} completed={len(all_points)-len(points)} "
        f"remaining={len(points)} jobs={args.jobs}",
        flush=True,
    )
    if not points:
        print(f"nothing to do: {results}")
        return 0

    with results.open(file_mode, newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, FIELDNAMES, lineterminator="\n")
        if file_mode == "w":
            writer.writeheader()
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {
                executor.submit(
                    run_point, point, args, run_root, log_root
                ): point
                for point in points
            }
            try:
                for index, future in enumerate(as_completed(futures), start=1):
                    point = futures[future]
                    row = future.result()
                    writer.writerow(row)
                    csv_file.flush()
                    print(
                        f"[{index}/{len(points)}] {point[0]} {point[1]} "
                        f"L{point[2]} rate={point[3]:.2f}",
                        flush=True,
                    )
            except BaseException:
                for future in futures:
                    future.cancel()
                raise
    sort_results(results)
    print(f"complete: {results}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
