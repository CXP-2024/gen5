# DP-Phys directional-bias and VC-scaling results

## Experiment

`torus3d_xbiased` was added to isolate the traffic condition that should favor
a paired Pool. It runs on an 8x4x4 Torus3D (128 nodes), sends every packet three
minimal hops in X, and chooses +X with a configurable probability. At 50% the
E/W pair is balanced; at 100% all routers receive the transit traffic from
West while East is idle. The flows remain spatially distributed across all X
rings, rather than converging on one hotspot output.

All results below use L=8, vnet 0 one-flit packets, 10,000 cycles, and three
seeds. The 128-node binary was built with `NUMBER_BITS_PER_SET=128`; this only
raises Ruby's destination-set capacity and does not change either compared
router design.

The main matrices contain 171 runs:

- 45 runs locating the four-VC saturation region at 100% +X;
- 54 runs scanning +X bias from 50% to 100% at offered injection 0.10;
- 72 runs scaling equal physical VC capacity to six and eight.

Additional short smoke/knee sweeps were used only to choose the long-run
points. Every main run completed without deadlock and passed Pool read-port,
allocation, migration, return, direction, and ownership-wait checks.

## Directional-bias crossover with four physical VCs

Each DP-Phys point is paired with `private_v4`. Cap 3 is the safe default; cap
4 is a fully elastic upper bound that can leave the cold side with no Pool
credit.

| +X probability | Cap 3 throughput/base | Cap 3 latency/base | Cap 4 throughput/base | Cap 4 latency/base |
|---:|---:|---:|---:|---:|
| 50% | 1.000 | 1.023 | 1.000 | 1.018 |
| 60% | 1.000 | 1.023 | 1.000 | 1.015 |
| 70% | 1.000 | 1.016 | 1.000 | 1.005 |
| 80% | 1.000 | 1.001 | 1.000 | 0.982 |
| 90% | 1.021 | 0.908 | 1.021 | 0.880 |
| 100% | 1.818 | 0.280 | 1.818 | 0.265 |

The 100% point is above private-v4 saturation, so its latency ratio must not be
presented as a below-saturation latency improvement. The valid high-load
metric there is delivered throughput: DP-Phys avoids the private design's
credit/buffer backpressure collapse and delivers about 1.82x as many packets
during the measured interval. At 90%, which is close to the private knee, cap
3 lowers network latency by about 9.2%; cap 4 lowers it by about 12.0%. The
throughput mean rises about 2.1%, but the three-seed confidence interval still
overlaps a smaller gain because the baseline is at its knee.

The crossover is the important result. From 50/50 through 70/30, there is not
enough stranded opposite-direction capacity to repay the 1R1W phase cost. At
80/20 cap 4 first becomes beneficial, and by 90/10 both the demand skew and the
credit round-trip are large enough for borrowing to dominate arbitration
overhead.

## Four-VC saturation range

Using completion/acceptance close to one as a coarse stability criterion, the
tested offered-rate range is:

| Four-VC design | Highest tested stable offered rate | Relative to private |
|---|---:|---:|
| private-v4 | about 0.08 | 1.00x |
| pressure cap 3 | about 0.10 | about 1.25x |
| pressure cap 4 | about 0.12 | about 1.50x |

These are preliminary brackets rather than exact saturation throughputs; a
finer 0.005 injection sweep and longer drain-aware runs are needed for the
paper figure. They nevertheless explain why the earlier 4x4x4 tornado result
showed only a 4.8% latency gain: that workload already hit a different output
bottleneck, whereas the distributed three-hop X pattern exposes input-credit
underutilization that movable storage can repair.

## VC-count scale ablation

Scaling preserves equal physical storage within every comparison:

| Physical VCs/port | Private adaptive + escape | DP RES per side | Pair Pool | Safe owner cap |
|---:|---:|---:|---:|---:|
| 4 | 3 + 1 | 1 private + 1 escape | 4 | 3 |
| 6 | 5 + 1 | 2 private + 1 escape | 6 | 4 |
| 8 | 7 + 1 | 3 private + 1 escape | 8 | 5 |

The safe scaled policy always allows one borrowed Pool credit. Full caps 6/8
are included only as elasticity upper bounds.

At offered rate 0.10, private-v6 and private-v8 are below saturation. DP-Phys
then has no useful capacity shortage to repair and raises latency by roughly
2--4%. This confirms that the Pool is not intrinsically faster.

Near each private design's saturation knee, the picture changes:

| VCs | Offered rate | Policy | Throughput/base | Latency/base | Injection acceptance |
|---:|---:|---|---:|---:|---:|
| 6 | 0.15 | safe one-borrow | 1.27 | 0.56 | 0.99 |
| 6 | 0.15 | full cap | 1.28 | 0.53 | 1.00 |
| 8 | 0.20 | safe one-borrow | 1.08 | 0.83 | 1.00 |
| 8 | 0.20 | full cap | 1.08 | 0.81 | 1.00 |

The corresponding private acceptance ratios are 0.79 for six VCs at 0.15 and
0.93 for eight VCs at 0.20. Because these points straddle saturation, delivered
throughput and the location of the knee are more meaningful than comparing
their absolute latencies.

The coarse stable-rate brackets move with capacity:

| VCs | Private | Safe one-borrow | Full elasticity |
|---:|---:|---:|---:|
| 4 | 0.08 | 0.10 | 0.12 |
| 6 | 0.12 | 0.15 | 0.20 |
| 8 | 0.18 | 0.20 | 0.25 |

The scale experiment therefore strengthens, rather than replaces, the v4
result. More private VCs delay the point where sharing is useful; close to that
new point, the movable Pool again extends the usable load range. The relative
benefit of borrowing only one credit generally shrinks as total VC count
increases, while fully elastic ownership retains a large upper bound at the
cost of cold-side fairness.

## Conclusion and next step

VC scaling is necessary as an ablation, but four physical VCs should remain
the main area-conscious design point. Increasing only DP-Phys VCs would be an
unfair comparison; every scale must retain an equal-capacity private baseline.

The next paper-quality sweep should refine each knee with 0.005 injection
steps, at least 50,000 measured cycles and five seeds, and include a drain
phase. The recommended main configuration remains pressure cap 3. Full caps
are useful as upper bounds, not as the safety-preserving proposal.
