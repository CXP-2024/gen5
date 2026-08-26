#!/usr/bin/env python3
"""Measure the fixed-total-VC tradeoff for 3D Torus adaptive routing."""

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
    raise RuntimeError("could not locate the gem5 repository root")


REPO_ROOT = find_repo_root()
GEM5 = REPO_ROOT / "build/NULL/gem5.opt"
CONFIG = REPO_ROOT / "configs/example/garnet_synth_traffic.py"
TASK_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = TASK_DIR / "artifacts"
RUN_DIR = ARTIFACT_DIR / "vc_ablation_runs"
LOG_DIR = ARTIFACT_DIR / "vc_ablation_logs"
RESULTS = TASK_DIR / "vc_ablation.csv"

NODES = 64
TOTAL_VCS = 4
SPLITS = (0, 1, 2, 3)
PATTERNS = ("torus3d_transpose", "torus3d_xopposite")
DEFAULT_RATES = (0.30, 0.40, 0.50, 0.75, 1.00)
STAT_NAMES = {
    "packets_injected": "system.ruby.network.packets_injected::total",
    "packets_received": "system.ruby.network.packets_received::total",
    "packet_latency": "system.ruby.network.average_packet_latency",
    "average_hops": "system.ruby.network.average_hops",
    "adaptive_hops": "system.ruby.network.adaptive_hops",
    "escape_hops": "system.ruby.network.escape_hops",
    "escape_transitions": "system.ruby.network.escape_transitions",
}
FIELDNAMES = [
    "adaptive_vcs",
    "escape_vcs",
    "deadlock_free_guarantee",
    "pattern",
    "injection_rate",
    "packets_injected",
    "packets_received",
    "injection_acceptance",
    "delivery_ratio",
    "throughput",
    "packet_latency",
    "average_hops",
    "adaptive_hops",
    "escape_hops",
    "escape_transitions",
    "escape_hop_fraction",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--patterns", nargs="+", choices=PATTERNS, default=PATTERNS
    )
    parser.add_argument(
        "--escape-vcs",
        nargs="+",
        type=int,
        default=SPLITS,
        help="escape VC counts to evaluate (default: 0 1 2 3)",
    )
    parser.add_argument(
        "--rates", nargs="+", type=float, default=DEFAULT_RATES
    )
    parser.add_argument("--sim-cycles", type=int, default=10000)
    parser.add_argument(
        "--jobs", type=int, default=min(3, os.cpu_count() or 1)
    )
    parser.add_argument("--results", type=Path, default=RESULTS)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--keep-runs", action="store_true")
    return parser.parse_args()


def parse_stats(path: Path) -> dict[str, float]:
    wanted = {value: key for key, value in STAT_NAMES.items()}
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


def read_rows(results: Path, force: bool) -> list[dict[str, str]]:
    if force or not results.exists():
        return []
    with results.open(newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def point_key(
    adaptive_vcs: int, escape_vcs: int, pattern: str, rate: float
) -> tuple[int, int, str, str]:
    return adaptive_vcs, escape_vcs, pattern, f"{rate:.2f}"


def run_point(
    escape_vcs: int,
    pattern: str,
    rate: float,
    sim_cycles: int,
    keep_runs: bool,
) -> dict[str, float | int | str]:
    adaptive_vcs = TOTAL_VCS - escape_vcs
    rate_text = f"{rate:.2f}"
    name = f"a{adaptive_vcs}_e{escape_vcs}_{pattern}_{rate_text}"
    point_run_dir = RUN_DIR / name
    log_path = LOG_DIR / f"{name}.log"
    point_run_dir.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

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
        "--routing-algorithm=4",
        f"--vcs-per-vnet={TOTAL_VCS}",
        f"--escape-vcs={escape_vcs}",
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
    expected = NODES * (sim_cycles / 2) * rate
    injected = stats["packets_injected"]
    received = stats["packets_received"]
    classified_hops = stats["adaptive_hops"] + stats["escape_hops"]
    row: dict[str, float | int | str] = {
        "adaptive_vcs": adaptive_vcs,
        "escape_vcs": escape_vcs,
        "deadlock_free_guarantee": "yes" if escape_vcs else "no",
        "pattern": pattern,
        "injection_rate": rate,
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


def write_rows(
    results: Path, rows: list[dict[str, float | int | str]]
) -> None:
    rows.sort(
        key=lambda row: (
            str(row["pattern"]),
            int(row["escape_vcs"]),
            float(row["injection_rate"]),
        )
    )
    temporary = results.with_suffix(".csv.tmp")
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
    if any(rate <= 0 or rate > 1 for rate in rates):
        raise SystemExit("all injection rates must be in the interval (0, 1]")
    if args.jobs < 1 or args.sim_cycles < 1:
        raise SystemExit("--jobs and --sim-cycles must be positive")
    if any(
        escape_vcs < 0 or escape_vcs >= TOTAL_VCS
        for escape_vcs in args.escape_vcs
    ):
        raise SystemExit("--escape-vcs values must be in the interval [0, 3]")

    existing_rows = read_rows(args.results, args.force)
    existing_keys = {
        point_key(
            int(row["adaptive_vcs"]),
            int(row["escape_vcs"]),
            row["pattern"],
            float(row["injection_rate"]),
        )
        for row in existing_rows
    }
    points = [
        (escape_vcs, pattern, rate)
        for pattern in args.patterns
        for escape_vcs in sorted(set(args.escape_vcs))
        for rate in rates
        if point_key(TOTAL_VCS - escape_vcs, escape_vcs, pattern, rate)
        not in existing_keys
    ]
    if not points:
        print(f"all requested points already exist in {args.results}")
        return 0

    print(f"running {len(points)} VC-ablation points with {args.jobs} jobs")
    new_rows: list[dict[str, float | int | str]] = []
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = {
            executor.submit(
                run_point,
                escape_vcs,
                pattern,
                rate,
                args.sim_cycles,
                args.keep_runs,
            ): (escape_vcs, pattern, rate)
            for escape_vcs, pattern, rate in points
        }
        for future in as_completed(futures):
            escape_vcs, pattern, rate = futures[future]
            row = future.result()
            new_rows.append(row)
            print(
                f"complete: A{TOTAL_VCS - escape_vcs}/E{escape_vcs} "
                f"{pattern} {rate:.2f}"
            )

    write_rows(args.results, [*existing_rows, *new_rows])
    print(
        f"wrote {len(existing_rows) + len(new_rows)} points to {args.results}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
