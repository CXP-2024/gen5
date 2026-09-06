#!/usr/bin/env python3
"""Single regression and invariant harness for the DP-Phys milestones.

The PRIV and CBS scopes compare deterministic network statistics against
checked-in reference files.  The DP-Phys scopes rely on the simulator's
mechanism assertions and add policy/statistical checks here.
"""

from __future__ import annotations

import argparse
import difflib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


def find_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "configs/example/garnet_synth_traffic.py").is_file():
            return candidate
    raise RuntimeError("could not locate the gem5 repository root")


ROOT = find_repo_root()
GEM5 = ROOT / "build/NULL/gem5.opt"
CONFIG = ROOT / "configs/example/garnet_synth_traffic.py"
HERE = Path(__file__).resolve().parent
BASELINES = HERE / "baselines"
DEFAULT_ARTIFACTS = HERE / "artifacts_regress"
NETWORK_PREFIX = "system.ruby.network."
QUEUE_DEPTH_PREFIX = NETWORK_PREFIX + "dpphys_grant_queue_depth"
ROUTER_ACTIVITY_STATS = {
    "buffer_reads",
    "buffer_writes",
    "crossbar_activity",
    "sw_input_arbiter_activity",
    "sw_output_arbiter_activity",
}


@dataclass(frozen=True)
class Point:
    name: str
    pattern: str
    rate: float
    latency: int = 8
    policy: str = ""
    routing: int = 4
    vcs: int = 4
    extra: tuple[str, ...] = ()


PRIV_POINTS = tuple(
    Point(f"priv-{pattern}", pattern, 0.10)
    for pattern in (
        "torus3d_xopposite",
        "torus3d_tornado",
        "torus3d_transpose",
        "torus3d_neighbor",
        "uniform_random",
    )
)

CBS_POINTS = tuple(
    Point(
        f"cbs-{pattern}",
        pattern,
        0.10,
        routing=3,
        extra=("--enable-cbs",),
    )
    for pattern in (
        "torus3d_xopposite",
        "torus3d_tornado",
        "uniform_random",
    )
)

STATIC_RATES = (0.05, 0.20, 0.40)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scope",
        required=True,
        choices=("priv", "cbs", "static-smoke", "invariant", "all"),
    )
    parser.add_argument("--sim-cycles", type=int, default=2_000)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument(
        "--record-baseline",
        action="store_true",
        help="replace PRIV/CBS deterministic reference files",
    )
    return parser.parse_args()


def command(point: Point, outdir: Path, cycles: int) -> list[str]:
    args = [
        str(GEM5),
        "-d",
        str(outdir),
        str(CONFIG),
        "--network=garnet",
        "--num-cpus=64",
        "--num-dirs=64",
        "--topology=Torus3D",
        "--torus-x=4",
        "--torus-y=4",
        "--torus-z=4",
        f"--routing-algorithm={point.routing}",
        f"--vcs-per-vnet={point.vcs}",
        "--escape-vcs=1",
        "--inj-vnet=0",
        f"--synthetic={point.pattern}",
        f"--sim-cycles={cycles}",
        "--random-seed=1",
        f"--injectionrate={point.rate:.2f}",
        f"--link-latency={point.latency}",
    ]
    if point.policy:
        args += [f"--dpphys-policy={point.policy}", "--dpphys-r=2"]
    return args + list(point.extra)


def parse_stats(path: Path) -> dict[str, float]:
    result: dict[str, float] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        try:
            result[fields[0]] = float(fields[1])
        except ValueError:
            continue
    return result


def canonical_stats(path: Path) -> str:
    """Keep deterministic network output and normalize its whitespace."""
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        name = fields[0]
        suffix = name.removeprefix(NETWORK_PREFIX)
        top_level = (
            name.startswith(NETWORK_PREFIX)
            and "." not in suffix
            and "traffic_distribution" not in suffix
        )
        router_activity = (
            suffix.startswith("routers")
            and suffix.rsplit(".", 1)[-1] in ROUTER_ACTIVITY_STATS
        )
        if (
            name == "simTicks" or top_level or router_activity
        ) and not name.startswith(QUEUE_DEPTH_PREFIX):
            lines.append(f"{name} {fields[1]}")
    return "\n".join(lines) + "\n"


def run(
    point: Point, artifact_dir: Path, cycles: int
) -> tuple[Path, dict[str, float]]:
    outdir = artifact_dir / point.name
    outdir.mkdir(parents=True, exist_ok=True)
    log = outdir / "run.log"
    result = subprocess.run(
        command(point, outdir, cycles),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    log.write_text(result.stdout, encoding="utf-8")
    if result.returncode:
        tail = "\n".join(result.stdout.splitlines()[-20:])
        raise RuntimeError(
            f"{point.name} failed (rc={result.returncode})\n{tail}"
        )
    stats_path = outdir / "stats.txt"
    if not stats_path.is_file():
        raise RuntimeError(f"{point.name} produced no stats.txt")
    stats = parse_stats(stats_path)
    if stats.get(NETWORK_PREFIX + "packets_received::total", 0) <= 0:
        raise RuntimeError(f"{point.name} received no packets")
    print(f"PASS run {point.name}")
    return stats_path, stats


def compare_baseline(point: Point, stats_path: Path, record: bool) -> None:
    baseline = BASELINES / f"{point.name}.stats"
    actual = canonical_stats(stats_path)
    if record:
        BASELINES.mkdir(parents=True, exist_ok=True)
        baseline.write_text(actual, encoding="utf-8")
        print(f"RECORDED {baseline.relative_to(ROOT)}")
        return
    if not baseline.is_file():
        raise RuntimeError(
            f"missing {baseline.relative_to(ROOT)}; run with --record-baseline"
        )
    expected = baseline.read_text(encoding="utf-8")
    if actual != expected:
        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(True),
                actual.splitlines(True),
                fromfile=str(baseline),
                tofile=str(stats_path),
            )
        )
        raise RuntimeError(
            f"deterministic stats changed for {point.name}:\n{diff}"
        )
    print(f"PASS bitwise {point.name}")


def baseline_scope(
    points: tuple[Point, ...], args: argparse.Namespace
) -> None:
    for point in points:
        stats_path, _ = run(point, args.artifact_dir, args.sim_cycles)
        compare_baseline(point, stats_path, args.record_baseline)


def static_smoke(args: argparse.Namespace) -> None:
    for rate in STATIC_RATES:
        private = Point(f"static-priv-{rate:.2f}", "uniform_random", rate)
        pooled = Point(
            f"static-dpphys-{rate:.2f}",
            "uniform_random",
            rate,
            policy="static",
            vcs=8,
        )
        _, private_stats = run(private, args.artifact_dir, args.sim_cycles)
        _, pooled_stats = run(pooled, args.artifact_dir, args.sim_cycles)
        migrated = pooled_stats.get(
            NETWORK_PREFIX + "dpphys_grants_migrated", -1
        )
        if migrated != 0:
            raise RuntimeError(f"static migrated {migrated} pool grants")
        key = NETWORK_PREFIX + "packets_received::total"
        delta = (pooled_stats[key] / private_stats[key] - 1.0) * 100.0
        print(
            f"DIAG static/private received delta at {rate:.2f}: {delta:+.2f}%"
        )


def invariant_scope(args: argparse.Namespace) -> None:
    points = (
        Point(
            "invariant-static",
            "uniform_random",
            0.20,
            policy="static",
            vcs=8,
        ),
        Point(
            "invariant-forced",
            "uniform_random",
            0.30,
            policy="forced",
            vcs=8,
        ),
        Point(
            "invariant-starve",
            "torus3d_tornado",
            1.00,
            policy="starve",
            vcs=8,
        ),
    )
    for point in points:
        _, stats = run(point, args.artifact_dir, args.sim_cycles)
        migrated = stats.get(NETWORK_PREFIX + "dpphys_grants_migrated", -1)
        if point.policy == "static" and migrated != 0:
            raise RuntimeError("static policy migrated a grant")
        if point.policy != "static" and migrated <= 0:
            raise RuntimeError(f"{point.policy} did not exercise migration")
        if point.policy == "starve" and point.latency == 8:
            depth = stats.get(
                NETWORK_PREFIX + "dpphys_grant_queue_depth::max_value", -1
            )
            if depth > 1:
                raise RuntimeError(
                    f"L=8 grant queue depth exceeded 1: {depth}"
                )


def main() -> int:
    args = parse_args()
    if not GEM5.is_file():
        raise RuntimeError("build/NULL/gem5.opt is missing; build it first")
    args.artifact_dir = args.artifact_dir.resolve()
    if args.scope in ("priv", "all"):
        baseline_scope(PRIV_POINTS, args)
    if args.scope in ("cbs", "all"):
        baseline_scope(CBS_POINTS, args)
    if args.scope in ("static-smoke", "all"):
        static_smoke(args)
    if args.scope in ("invariant", "all"):
        invariant_scope(args)
    print(f"PASS scope={args.scope}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
