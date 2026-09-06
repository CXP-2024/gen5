#!/usr/bin/env python3
"""Sweep the equal-physical paired-pool DP-Phys implementation.

All modes retain four physical VC slots per input port. The private baseline
uses four ordinary VCs. DP-Phys splits the same pair capacity into one private
adaptive VC plus one private escape VC per direction and four movable pool
slots per opposing direction pair. Internal links expose logical pool IDs, but
do not add physical storage. DP-Phys reads use complementary two-phase RR:
side 0 RES / side 1 POOL, then side 0 POOL / side 1 RES.

The default matrix compares private, RTS, owner-RR, and
reserved-pressure/sticky credit ownership policies at link latencies 1 and 8.
A gem5 deadlock panic is recorded as a result; another non-zero exit is treated
as a harness failure.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
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
DEFAULT_ARTIFACT_DIR = TASK_DIR / "artifacts_dpphys"
DEFAULT_RESULTS = TASK_DIR / "results_dpphys.csv"

DPPHYS_BASE_FLAGS = [
    "--enable-dpphys",
    "--dpphys-private-vcs=1",
    "--dpphys-pool-vcs=4",
]


def dpphys_flags(policy: str, owner_cap: int = 3) -> list[str]:
    return DPPHYS_BASE_FLAGS + [
        f"--dpphys-owner-cap={owner_cap}",
        f"--dpphys-policy={policy}",
    ]


MODE_TABLE: dict[str, list[str]] = {
    "private_v4": [],
    "dpphys_rts": dpphys_flags("rts"),
    "dpphys_owner_rr": dpphys_flags("rr"),
    "dpphys_pressure": dpphys_flags("pressure"),
    "dpphys_pressure_cap2": dpphys_flags("pressure", 2),
    "dpphys_pressure_cap4": dpphys_flags("pressure", 4),
    "private_v6": [],
    "dpphys_pressure_v6": [
        "--enable-dpphys",
        "--dpphys-private-vcs=2",
        "--dpphys-pool-vcs=6",
        "--dpphys-owner-cap=4",
        "--dpphys-policy=pressure",
    ],
    "dpphys_pressure_v6_full": [
        "--enable-dpphys",
        "--dpphys-private-vcs=2",
        "--dpphys-pool-vcs=6",
        "--dpphys-owner-cap=6",
        "--dpphys-policy=pressure",
    ],
    "private_v8": [],
    "dpphys_pressure_v8": [
        "--enable-dpphys",
        "--dpphys-private-vcs=3",
        "--dpphys-pool-vcs=8",
        "--dpphys-owner-cap=5",
        "--dpphys-policy=pressure",
    ],
    "dpphys_pressure_v8_full": [
        "--enable-dpphys",
        "--dpphys-private-vcs=3",
        "--dpphys-pool-vcs=8",
        "--dpphys-owner-cap=8",
        "--dpphys-policy=pressure",
    ],
}
MODE_PHYSICAL_VCS = {
    mode: 6 if "v6" in mode else 8 if "v8" in mode else 4
    for mode in MODE_TABLE
}
MODES = list(MODE_TABLE)
DEFAULT_MODES = [
    "private_v4",
    "dpphys_rts",
    "dpphys_owner_rr",
    "dpphys_pressure",
]
DEFAULT_PATTERNS = [
    "torus3d_xopposite",
    "torus3d_tornado",
    "torus3d_transpose",
    "torus3d_neighbor",
    "uniform_random",
]
PATTERNS = DEFAULT_PATTERNS + ["torus3d_x_reversal", "torus3d_xbiased"]
DEFAULT_RATES = [index / 20 for index in range(1, 21)]

STAT_NAMES = {
    "sim_ticks": "simTicks",
    "packets_injected": "system.ruby.network.packets_injected::total",
    "packets_received": "system.ruby.network.packets_received::total",
    "queueing_latency": "system.ruby.network.average_packet_queueing_latency",
    "network_latency": "system.ruby.network.average_packet_network_latency",
    "packet_latency": "system.ruby.network.average_packet_latency",
    "average_hops": "system.ruby.network.average_hops",
    "escape_hops": "system.ruby.network.escape_hops",
    "escape_transitions": "system.ruby.network.escape_transitions",
    "pool_allocations": "system.ruby.network.dpphys_pool_allocations",
    "owned_pool_allocations": (
        "system.ruby.network.dpphys_owned_pool_allocations"
    ),
    "demand_reclaims": "system.ruby.network.dpphys_demand_reclaims",
    "owner_migrations": "system.ruby.network.dpphys_owner_migrations",
    "release_handoffs": "system.ruby.network.dpphys_release_handoffs",
    "release_keeps": "system.ruby.network.dpphys_release_keeps",
    "ownership_wait_starts": (
        "system.ruby.network.dpphys_ownership_wait_starts"
    ),
    "ownership_wait_completions": (
        "system.ruby.network.dpphys_ownership_wait_completions"
    ),
    "ownership_wait_cycles": (
        "system.ruby.network.dpphys_ownership_wait_cycles"
    ),
    "ownership_wait_max": "system.ruby.network.dpphys_ownership_wait_max",
    "pool_write_blocks": "system.ruby.network.dpphys_pool_write_blocks",
    "pool_read_conflicts": "system.ruby.network.dpphys_pool_read_conflicts",
    "pool_reads": "system.ruby.network.dpphys_pool_reads",
    "reserved_reads": "system.ruby.network.dpphys_reserved_reads",
    "borrowed_peak": "system.ruby.network.dpphys_borrowed_peak",
}
DIRECTION_NAMES = {
    "east": "East",
    "west": "West",
    "north": "North",
    "south": "South",
    "up": "Up",
    "down": "Down",
}
DIRECTIONAL_STATS = {
    "pool_allocations": "dpphys_pool_allocations_by_dir",
    "pool_reads": "dpphys_pool_reads_by_dir",
    "reserved_reads": "dpphys_reserved_reads_by_dir",
    "migrations_to": "dpphys_migrations_to_dir",
}
for metric, stat_name in DIRECTIONAL_STATS.items():
    for direction, stat_subname in DIRECTION_NAMES.items():
        STAT_NAMES[
            f"{metric}_{direction}"
        ] = f"system.ruby.network.{stat_name}::{stat_subname}"

FIELDNAMES = [
    "mode",
    "physical_vcs",
    "pattern",
    "injection_rate",
    "link_latency",
    "sim_cycles",
    "torus_x",
    "torus_y",
    "torus_z",
    "traffic_epoch_cycles",
    "traffic_x_bias",
    "traffic_x_hops",
    "seed",
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
    "escape_hops",
    "escape_transitions",
    "pool_allocations",
    "owned_pool_allocations",
    "demand_reclaims",
    "owner_migrations",
    "release_handoffs",
    "release_keeps",
    "ownership_wait_starts",
    "ownership_wait_completions",
    "ownership_wait_cycles",
    "ownership_wait_max",
    "pool_write_blocks",
    "pool_read_conflicts",
    "pool_reads",
    "reserved_reads",
    "borrowed_peak",
    "sim_ticks",
    *[
        f"{metric}_{direction}"
        for metric in DIRECTIONAL_STATS
        for direction in DIRECTION_NAMES
    ],
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--modes", nargs="+", choices=MODES, default=DEFAULT_MODES
    )
    parser.add_argument(
        "--patterns", nargs="+", choices=PATTERNS, default=DEFAULT_PATTERNS
    )
    parser.add_argument(
        "--rates", nargs="+", type=float, default=DEFAULT_RATES
    )
    parser.add_argument(
        "--link-latencies", nargs="+", type=int, default=[1, 8]
    )
    parser.add_argument("--sim-cycles", type=int, default=10_000)
    parser.add_argument("--epoch-cycles", nargs="+", type=int, default=[64])
    parser.add_argument("--x-biases", nargs="+", type=float, default=[1.0])
    parser.add_argument("--x-hops", nargs="+", type=int, default=[1])
    parser.add_argument("--seeds", nargs="+", type=int, default=[1])
    parser.add_argument("--nodes", type=int, default=64)
    parser.add_argument("--torus-x", type=int, default=4)
    parser.add_argument("--torus-y", type=int, default=4)
    parser.add_argument("--torus-z", type=int, default=4)
    parser.add_argument(
        "--jobs", type=int, default=min(8, os.cpu_count() or 1)
    )
    parser.add_argument(
        "--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR
    )
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
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


def existing_points(results: Path, force: bool) -> set[tuple[str, ...]]:
    if force or not results.exists():
        return set()
    with results.open(newline="", encoding="utf-8") as csv_file:
        return {
            (
                row["mode"],
                row.get("physical_vcs", "4"),
                row["pattern"],
                f"{float(row['injection_rate']):.2f}",
                row["link_latency"],
                row["sim_cycles"],
                row.get("torus_x", "4"),
                row.get("torus_y", "4"),
                row.get("torus_z", "4"),
                row.get("traffic_epoch_cycles", "0"),
                row.get("traffic_x_bias", "0"),
                row.get("traffic_x_hops", "0"),
                row.get("seed", "1"),
            )
            for row in csv.DictReader(csv_file)
        }


def run_point(
    mode: str,
    pattern: str,
    rate: float,
    link_latency: int,
    sim_cycles: int,
    traffic_epoch_cycles: int,
    traffic_x_bias: float,
    traffic_x_hops: int,
    seed: int,
    nodes: int,
    torus_x: int,
    torus_y: int,
    torus_z: int,
    artifact_dir: Path,
    keep_runs: bool,
) -> dict[str, float | str]:
    run_root = artifact_dir / "runs"
    log_root = artifact_dir / "logs"
    log_root.mkdir(parents=True, exist_ok=True)
    rate_text = f"{rate:.2f}"
    name = (
        f"{mode}_{pattern}_{rate_text}_l{link_latency}_c{sim_cycles}"
        f"_x{torus_x}y{torus_y}z{torus_z}_e{traffic_epoch_cycles}"
        f"_b{traffic_x_bias:g}_h{traffic_x_hops}_s{seed}"
    )
    run_dir = run_root / name
    run_dir.mkdir(parents=True, exist_ok=True)
    stats_path = run_dir / "stats.txt"
    stats_path.unlink(missing_ok=True)
    log_path = log_root / f"{name}.log"
    command = [
        str(GEM5),
        "-d",
        str(run_dir),
        str(CONFIG),
        "--network=garnet",
        f"--num-cpus={nodes}",
        f"--num-dirs={nodes}",
        "--topology=Torus3D",
        f"--torus-x={torus_x}",
        f"--torus-y={torus_y}",
        f"--torus-z={torus_z}",
        "--routing-algorithm=4",
        f"--vcs-per-vnet={MODE_PHYSICAL_VCS[mode]}",
        "--escape-vcs=1",
        "--inj-vnet=0",
        f"--synthetic={pattern}",
        f"--sim-cycles={sim_cycles}",
        f"--random-seed={seed}",
        f"--injectionrate={rate_text}",
        f"--link-latency={link_latency}",
    ] + MODE_TABLE[mode]
    if pattern == "torus3d_x_reversal":
        command.append(f"--traffic-epoch-cycles={traffic_epoch_cycles}")
    if pattern == "torus3d_xbiased":
        command.extend(
            [
                f"--traffic-x-bias={traffic_x_bias:g}",
                f"--traffic-x-hops={traffic_x_hops}",
            ]
        )
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

    stats = parse_stats(stats_path) if stats_path.is_file() else {}
    directional_keys = {
        f"{metric}_{direction}"
        for metric in DIRECTIONAL_STATS
        for direction in DIRECTION_NAMES
    }
    for key in STAT_NAMES:
        stats.setdefault(key, 0.0 if key in directional_keys else math.nan)
    system_cycles = sim_cycles / 2
    expected = nodes * system_cycles * rate
    injected = stats["packets_injected"]
    received = stats["packets_received"]
    row: dict[str, float | str] = {
        "mode": mode,
        "physical_vcs": MODE_PHYSICAL_VCS[mode],
        "pattern": pattern,
        "injection_rate": rate,
        "link_latency": link_latency,
        "sim_cycles": sim_cycles,
        "torus_x": torus_x,
        "torus_y": torus_y,
        "torus_z": torus_z,
        "traffic_epoch_cycles": traffic_epoch_cycles,
        "traffic_x_bias": traffic_x_bias,
        "traffic_x_hops": traffic_x_hops,
        "seed": seed,
        "deadlock": deadlock,
        "expected_generated": expected,
        **stats,
        "injection_acceptance": injected / expected if expected else math.nan,
        "delivery_ratio": received / injected if injected else math.nan,
        "throughput": received / nodes / sim_cycles,
    }
    if not keep_runs:
        shutil.rmtree(run_dir, ignore_errors=True)
    return row


def sort_results(results: Path) -> None:
    with results.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))
    mode_order = {mode: index for index, mode in enumerate(MODES)}
    pattern_order = {pattern: index for index, pattern in enumerate(PATTERNS)}
    rows.sort(
        key=lambda row: (
            pattern_order[row["pattern"]],
            int(row["link_latency"]),
            int(row.get("physical_vcs", "4")),
            mode_order[row["mode"]],
            int(row["sim_cycles"]),
            int(row.get("torus_x", "4")),
            int(row.get("torus_y", "4")),
            int(row.get("torus_z", "4")),
            int(row.get("traffic_epoch_cycles", "0")),
            float(row.get("traffic_x_bias", "0")),
            int(row.get("traffic_x_hops", "0")),
            float(row["injection_rate"]),
            int(row.get("seed", "1")),
        )
    )
    temporary = results.with_suffix(results.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file, fieldnames=FIELDNAMES, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(results)


def main() -> int:
    args = parse_args()
    rates = sorted(set(args.rates))
    latencies = sorted(set(args.link_latencies))
    epochs = sorted(set(args.epoch_cycles))
    biases = sorted(set(args.x_biases))
    x_hops = sorted(set(args.x_hops))
    seeds = sorted(set(args.seeds))
    if any(rate <= 0 or rate > 1 for rate in rates):
        raise SystemExit("all rates must lie in (0, 1]")
    if any(latency < 1 for latency in latencies):
        raise SystemExit("all link latencies must be positive")
    if any(epoch < 1 for epoch in epochs):
        raise SystemExit("all traffic epochs must be positive")
    if any(bias < 0 or bias > 1 for bias in biases):
        raise SystemExit("all X biases must lie in [0, 1]")
    if any(hops < 1 or 2 * hops >= args.torus_x for hops in x_hops):
        raise SystemExit("all X hops must satisfy 0 < 2 * hops < torus-x")
    if args.nodes != args.torus_x * args.torus_y * args.torus_z:
        raise SystemExit("the Torus3D dimension product must equal --nodes")

    artifact_dir = args.artifact_dir.resolve()
    results = args.results.resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    results.parent.mkdir(parents=True, exist_ok=True)
    completed = existing_points(results, args.force)
    all_points = []
    for pattern in args.patterns:
        pattern_epochs = epochs if pattern == "torus3d_x_reversal" else [0]
        pattern_biases = biases if pattern == "torus3d_xbiased" else [0.0]
        pattern_hops = x_hops if pattern == "torus3d_xbiased" else [0]
        for latency in latencies:
            for mode in args.modes:
                for rate in rates:
                    for epoch in pattern_epochs:
                        for bias in pattern_biases:
                            for hops in pattern_hops:
                                for seed in seeds:
                                    all_points.append(
                                        (
                                            mode,
                                            pattern,
                                            rate,
                                            latency,
                                            epoch,
                                            bias,
                                            hops,
                                            seed,
                                        )
                                    )
    points = [
        point
        for point in all_points
        if (
            point[0],
            str(MODE_PHYSICAL_VCS[point[0]]),
            point[1],
            f"{point[2]:.2f}",
            str(point[3]),
            str(args.sim_cycles),
            str(args.torus_x),
            str(args.torus_y),
            str(args.torus_z),
            str(point[4]),
            f"{point[5]:g}",
            str(point[6]),
            str(point[7]),
        )
        not in completed
    ]
    file_mode = "w" if args.force or not results.exists() else "a"
    print(
        f"{len(all_points) - len(points)} completed; {len(points)} remaining; "
        f"running {args.jobs} job(s)",
        flush=True,
    )
    with results.open(file_mode, newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file, fieldnames=FIELDNAMES, lineterminator="\n"
        )
        if file_mode == "w":
            writer.writeheader()
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {
                executor.submit(
                    run_point,
                    mode,
                    pattern,
                    rate,
                    latency,
                    args.sim_cycles,
                    epoch,
                    bias,
                    hops,
                    seed,
                    args.nodes,
                    args.torus_x,
                    args.torus_y,
                    args.torus_z,
                    artifact_dir,
                    args.keep_runs,
                ): (mode, pattern, rate, latency, epoch, bias, hops, seed)
                for mode, pattern, rate, latency, epoch, bias, hops, seed in points
            }
            for future in as_completed(futures):
                row = future.result()
                writer.writerow(row)
                csv_file.flush()
                print(
                    f"done {row['mode']} {row['pattern']} "
                    f"rate={row['injection_rate']:.2f} "
                    f"L={row['link_latency']} "
                    f"epoch={row['traffic_epoch_cycles']} "
                    f"bias={row['traffic_x_bias']:.2f} "
                    f"hops={row['traffic_x_hops']} "
                    f"seed={row['seed']}",
                    flush=True,
                )
    sort_results(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
