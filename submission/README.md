# Lab 1–4 Submission Bundle

- **Author:** Wang Liming (王立明), 2024011338 — Lab 4 jointly with Changxun Pan (50 % / 50 %)
- **Date:** 2026-09-11
- **Base:** gem5 v23.0.0.1 (commit `af72b9ba58`), Garnet standalone (NULL ISA)

## Files

| File | Content |
|---|---|
| `Lab1_Report_2024011338.pdf` | Lab 1 report |
| `Lab2_Report_2024011338.pdf` | Lab 2 report |
| `Lab3_Report_2024011338.pdf` | Lab 3 report |
| `Lab3_SourceCode.tar.gz` | Lab 3 source code, only modified/added files (11 files, incl. the new `configs/topologies/Ring.py`) |
| `Lab3_2024011338.zip` | Lab 3 submission = report + source tarball |
| `Lab1-3_gem5_v23.0.0.1.patch` | All Lab 1–3 code changes in one git patch (12 files, +386/−43): Lab 1 tick frequency + statistics units / reception rate; Lab 3 Ring topology + routing + wormhole flow control. Lab 2 modified no source. |
| `Lab4_Report_2024011338.pdf` | Lab 4 report: *Tidal: Direction-Paired Virtual-Channel Buffer Pooling with a 1R1W Shared Pool* (9 pp.) |
| `Lab4_Tidal_1R1W_gem5_v23.0.0.1.patch` | All Lab 4 code in one git patch (28 files, +3,806/−124): the 1R1W direction-paired shared-pool VC design exactly as reported in the paper, Torus3D/Mesh3D/Ring topologies, Torus3D adaptive routing, synthetic-traffic extensions, and the sweep/analyzer scripts (`lab/DP/physical_bound/`). |

## Lab 1–3: applying the patch

On a clean gem5 v23.0.0.1 checkout (LF line endings):

```bash
git apply Lab1-3_gem5_v23.0.0.1.patch
scons build/NULL/gem5.opt PROTOCOL=Garnet_standalone -j$(nproc)
```

Verified: applied to a pristine v23.0.0.1 tree, all 12 files are
byte-identical to the tree the reported experiments were built from.

## Lab 4 (Tidal 1R1W): applying and running

Use a **separate** clean gem5 v23.0.0.1 checkout — do **not** combine with
the Lab 1–3 patch. Both add `configs/topologies/Ring.py` and touch the same
Garnet files; they are different assignments and conflict by design.

```bash
git apply Lab4_Tidal_1R1W_gem5_v23.0.0.1.patch
scons build/NULL/gem5.opt PROTOCOL=Garnet_standalone -j$(nproc)
```

For 128-node (8×4×4) runs, build with a larger Ruby destination set:

```bash
scons build/NULL/gem5.opt PROTOCOL=Garnet_standalone NUMBER_BITS_PER_SET=128 -j$(nproc)
```

Verified: applied to a pristine v23.0.0.1 tree, all 28 files are
byte-identical to snapshot commit `dc43a290`, which produced every number in
the paper.

### Single 1R1W run

Tidal with the pressure policy and owner cap 3 — the proposed configuration
(4×4×4 torus, tornado traffic, link latency 8):

```bash
./build/NULL/gem5.opt configs/example/garnet_synth_traffic.py \
  --network=garnet --num-cpus=64 --num-dirs=64 \
  --topology=Torus3D --torus-x=4 --torus-y=4 --torus-z=4 \
  --routing-algorithm=4 --vcs-per-vnet=4 --escape-vcs=1 \
  --inj-vnet=0 --synthetic=torus3d_tornado \
  --sim-cycles=10000 --injectionrate=0.5 --link-latency=8 \
  --enable-dpphys --dpphys-private-vcs=1 --dpphys-pool-vcs=4 \
  --dpphys-owner-cap=3 --dpphys-policy=pressure
```

- The equal-storage private baseline is the same command **without** the five
  `--*dpphys*` flags.
- `--dpphys-policy` accepts `rr` (blind owner round-robin) and `pressure`;
  `--dpphys-owner-cap` 2/3/4 reproduces the cap ablation.
- The X-biased workload of the paper uses `--synthetic=torus3d_xbiased
  --traffic-x-bias=0.9 --traffic-x-hops=3` on 8×4×4
  (`--num-cpus=128 --num-dirs=128 --torus-x=8`), built with
  `NUMBER_BITS_PER_SET=128`.
- Tidal statistics appear in `m5out/stats.txt` under
  `system.ruby.network.dpphys_*` (pool allocations, demand reclaims, owner
  migrations, release handoffs/keeps, bank reads, write blocks).

### Full sweeps

One CSV row per run; the runner records every gem5 command it issues:

```bash
python3 lab/DP/physical_bound/run_sweep_dpphys.py \
  --modes private_v4 dpphys_pressure dpphys_pressure_cap4 \
  --patterns torus3d_tornado --rates 0.1 0.5 0.9 \
  --link-latencies 8 --seeds 1 2 3 --jobs 8 \
  --results results.csv

python3 lab/DP/physical_bound/analyze_dpphys.py results.csv
```
