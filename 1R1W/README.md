# DP-Phys 1R1W reproducibility snapshot

This directory is a normal tracked directory of the main gem5 repository. It
is not a nested Git repository and it does not replace the current DP-Phys
implementation.

## Provenance

- Exact 1R1W snapshot commit:
  `dc43a290079518e0022b520e67275afded957d2e`
- Base gem5 commit:
  `2eb6a4e320dfe3578095dbf66a856ffec512a3dd`
- Snapshot date: 2026-09-06

`overlay/` mirrors repository-relative paths. It contains the DP-Phys source,
configuration changes, synthetic traffic generators, sweep/analyzer scripts,
reports, and raw CSV files from the 1R1W campaign.

The model in this snapshot has one Pool read service and one Pool write
service per direction pair and control vnet per cycle. Read access uses the
strict complementary phase schedule:

```text
even: side 0 RES,  side 1 POOL
odd:  side 0 POOL, side 1 RES
```

## Safe reconstruction

Do not copy the overlay onto the current `/root/gem5` checkout. Create a
temporary worktree from the recorded base commit; this uses the existing Git
repository and does not create another repository:

```bash
cd /root/gem5
git worktree add --detach /tmp/gem5-1r1w-build \
  2eb6a4e320dfe3578095dbf66a856ffec512a3dd
cp -a /root/gem5/1R1W/overlay/. /tmp/gem5-1r1w-build/
cd /tmp/gem5-1r1w-build
scons build/NULL/gem5.opt PROTOCOL=Garnet_standalone -j16
```

For the 128-node `torus3d_xbiased` experiment, build with the larger Ruby
destination set:

```bash
scons build/NULL/gem5.opt PROTOCOL=Garnet_standalone \
  NUMBER_BITS_PER_SET=128 -j16
```

## Main experiment entry points

- Runner: `overlay/lab/DP/physical_bound/run_sweep_dpphys.py`
- Analyzer: `overlay/lab/DP/physical_bound/analyze_dpphys.py`
- Implementation contract:
  `overlay/lab/DP/physical_bound/implementation.md`
- Evaluation plan: `overlay/lab/DP/physical_bound/evaluation_plan.md`
- Consolidated directional-bias results:
  `overlay/lab/DP/physical_bound/xbiased_scaling_results.md`

The runner records the exact command in each log. The historical CSV files
remain under `overlay/lab/DP/physical_bound/` and include the equal-capacity
`private_v4` baseline for paired comparisons.

## Representative rerun

After reconstructing the temporary worktree, this command reruns the final
four-VC 1R1W policy comparison for x-opposite traffic:

```bash
python3 lab/DP/physical_bound/run_sweep_dpphys.py \
  --modes private_v4 dpphys_rts dpphys_owner_rr dpphys_pressure \
  --patterns torus3d_xopposite \
  --rates 0.1 0.3 0.5 0.7 0.9 \
  --link-latencies 1 8 \
  --sim-cycles 3000 --seeds 1 --jobs 8 \
  --artifact-dir lab/DP/physical_bound/artifacts_xopposite_repro \
  --results lab/DP/physical_bound/results_xopposite_repro.csv --force
```

Use the longer three-seed commands documented in the included reports for
paper-quality confirmation. The existing 3,000-cycle validation matrix is a
smoke study, not a final statistical result.
