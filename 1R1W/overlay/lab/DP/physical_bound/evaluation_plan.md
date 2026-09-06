# DP-Phys v4 implementation and evaluation plan

This document separates two questions that the presentation must answer:

1. **Implementation:** does the simulator implement the intended paired pool,
   phase-RR access, and credit lifecycle without silently adding storage or
   ports?
2. **Evaluation:** when does movable pool ownership help, what does it cost,
   and why do the ownership policies behave differently?

The fair baseline is `private_v4`: four physical VC slots per directional
input port, including one escape VC. DP-Phys also has four physical slots per
port: one private adaptive VC, two locally resident pool slots, and one private
escape VC. Results must always be described as **equal physical storage**.

## Credit lifecycle and policy controls

A pool credit names one free physical pool slot and has exactly one logical
owner. The owner may allocate into it; occupancy/free information still returns
over Garnet's real credit link.

1. On allocation, use a private adaptive VC first.
2. If private is unavailable, use a free owned pool credit.
3. Under `pressure`, if no owned pool credit is usable, reclaim an idle
   peer-owned credit, subject to `owner_cap`.
4. When the packet leaves the input VC, the slot becomes free. `rts` keeps the
   credit with the last sender, `rr` gives successive released credits to
   alternating sides, and `pressure` gives it to the peer only when the peer's
   reserved region is more occupied. Equal pressure keeps the last owner.
5. Escape credit never migrates. This preserves a private escape path even if
   pool ownership is badly chosen.

The current owner-grant table is zero-latency. Therefore evaluation results are
an upper bound for a physical implementation until grant-wire delay and energy
are modeled explicitly.

## Research questions and hypotheses

| ID | Question | Main hypothesis |
|---|---|---|
| RQ1 | Is phase-RR and the single pool 1R/1W service implemented correctly? | Pool read conflicts remain zero; at most one pool allocation occurs per pair/vnet/cycle; RES and POOL reads both make progress. |
| RQ2 | Does sharing help with the same physical storage? | It helps under directional imbalance and long credit round trips, where an active side can use an idle peer's slots. |
| RQ3 | How should credit ownership be distributed and recovered? | Pressure+sticky follows demand; return-to-sender is stable but cannot redistribute; blind owner-RR can transfer capacity to an idle direction and strand it there. |
| RQ4 | What does the one-read Pool cost? | At short link latency or balanced traffic, phase selection adds waiting and can increase latency without improving throughput. |
| RQ5 | How much borrowing is safe? | Cap 3 is the expected compromise: one borrowed slot is allowed while every side retains at least one of four pool credits. Cap 4 may improve one-sided load but can hurt the peer's fairness. |
| RQ6 | Does a policy react quickly to changing traffic? | Sticky pressure should retain credit across bursts but must reclaim it within a bounded number of releases after the hot direction reverses. |

## Instrumentation and invariants

The runner records ordinary Garnet throughput/latency statistics plus the
following DP-Phys counters:

| Counter | Interpretation |
|---|---|
| `pool_allocations` | All writes admitted to a pool slot. |
| `owned_pool_allocations` | Pool writes using a credit already owned by that direction. |
| `demand_reclaims` | Pool writes that immediately reclaim an idle peer-owned credit. |
| `owner_migrations` | All logical owner changes. |
| `release_handoffs` | Owner changes made when a slot is freed. |
| `release_keeps` | Freed credits retained by the last user. |
| `pool_write_blocks` | Allocation attempts rejected because the pool write port was already used that cycle. |
| `pool_read_conflicts` | Must remain zero under complementary phase-RR. |
| `pool_reads`, `reserved_reads` | Successful switch grants from each bank. |
| `borrowed_peak` | Maximum credits held above a side's initial two-credit share. |

Allocation, read, reserved-read, and migration counts are also split across
E/W/N/S/U/D. For the one-flit control vnet used here, each completed run should
satisfy these conservation checks:

```text
pool_allocations = owned_pool_allocations + demand_reclaims
owner_migrations = demand_reclaims + release_handoffs
pool_reads = release_handoffs + release_keeps
pool_read_conflicts = 0
borrowed_peak <= owner_cap - 2
```

The final equality excludes pool flits still resident at simulation exit:

```text
pool_allocations - pool_reads = in-flight or buffered pool flits
```

For a directed pair, use the directional counters to report allocation share,
migration direction, and Jain fairness. Aggregate totals alone can hide one
starved side.

## Experiment matrix

### E0: structural and safety validation

- One short run for every policy and link latency.
- Assert all conservation equations above.
- Assert no deadlock/panic for all five traffic patterns at injection 1.0 and
  at least 20,000 cycles.
- Confirm the legacy non-DP mode still runs and invalid five-physical-VC
  DP-Phys configuration is rejected.
- Inspect per-direction counters for `torus3d_tornado`: on a 4x4x4 torus its
  destination is +1 in X/Y/Z, so Pool service should be strongly one-sided.

### E1: equal-capacity throughput-latency curves

Compare `private_v4`, `dpphys_rts`, `dpphys_owner_rr`, and
`dpphys_pressure` using:

- topology: 4x4x4 Torus3D, 64 nodes;
- control vnet 0, one-flit packets;
- physical VCs: 4 per input port in every mode;
- link latency: 1 and 8 cycles, optionally 16 for sensitivity;
- injection rate: 0.05 to 1.00 in 0.05 increments, then refine in 0.01 steps
  around the saturation knee;
- final runs: at least 50,000 measured cycles and seeds 1--5.

Report accepted injection, delivered throughput, network latency, total packet
latency, delivery ratio, and the injection rate at which latency first exceeds
2x the low-load value. Plot one throughput curve and one latency curve per
traffic/latency pair.

Traffic roles:

| Traffic | Why it is needed |
|---|---|
| `uniform_random` | Balanced general-load control; sharing should not create a large gain. |
| `torus3d_xopposite` | Tie-heavy X traffic that exercises both directions under adaptive routing. |
| `torus3d_tornado` | Deliberately one-sided +X/+Y/+Z load; primary sharing-benefit case. |
| `torus3d_neighbor` | One-hop directed traffic; exposes pure arbitration overhead. |
| `torus3d_transpose` | Mixed multidimensional path stress. |

### E2: ownership-policy explanation

At low load, near the baseline saturation knee, and above saturation, compare:

- `rts`: no release-time redistribution;
- `owner_rr`: traffic-oblivious release redistribution;
- `pressure`: reserved-fullness transfer plus equal-pressure stickiness and
  on-demand reclaim.

For each policy report:

```text
reclaim_fraction = demand_reclaims / pool_allocations
release_handoff_fraction = release_handoffs / pool_reads
sticky_keep_fraction = release_keeps / pool_reads
migration_cost = owner_migrations / packets_received
pool_service_share = pool_reads / (pool_reads + reserved_reads)
directional_allocation_share[d] = pool_allocations[d] / pool_allocations
```

Correlate these values with throughput and latency. The important causal test
is not merely that pressure is faster, but that it moves credits toward the
actually active directions while owner-RR can move them away.

### E3: owner-cap ablation

Use `dpphys_pressure_cap2`, `dpphys_pressure` (cap 3), and
`dpphys_pressure_cap4`.

- Cap 2: fixed 2/2 pool ownership; control for the value of migration.
- Cap 3: one side may own 3/4, but the peer retains one pool credit.
- Cap 4: fully elastic pool; maximum skew benefit and worst fairness risk.

Run balanced and tornado traffic at link latencies 1 and 8. Plot throughput and
latency against cap, and report per-direction service fairness. Cap 3 is only
justified if it captures most cap-4 benefit without cap-4 starvation.

### E4: dynamic reversal and burst stickiness

The implemented `torus3d_x_reversal` microbenchmark synchronously alternates
every source between one-hop +X and -X traffic. Phase A therefore enters the
next router from West; phase B enters it from East. Use
`--traffic-epoch-cycles` values 4, 16, 64, and 256. A separate extension is
still needed for explicit packet bursts of 1, 4, 8, and 16 packets.

Measure ownership after the reversal, ownership-wait episodes and their
mean/maximum completion time, packets blocked during recovery, and migrations
per useful pool allocation. The optional `DPPhys` event trace exposes each
demand and release migration. This directly tests the intuition that the last
user should retain a credit for the next packet, but must yield when the peer's
reserved region blocks.

### E5: read/write bottleneck and design ablations

- Compare short and long link latency to separate arbitration delay from
  buffering value.
- Sweep injection around saturation and report Pool read utilization and Pool
  write blocks.
- If a dual-read ideal model is added, compare it with 1R/1W to quantify the
  exact performance price paid for the smaller Pool implementation.
- Model one-cycle owner-grant transport as a sensitivity study; the current
  zero-cycle grant result is the optimistic bound.

### E6: directional-bias crossover and VC scaling

Use the implemented `torus3d_xbiased` pattern on an 8x4x4 Torus3D. Each packet
travels three X hops; sweep +X probability from 50% to 100% to find where
opposite-direction stranded capacity becomes more valuable than the 1R1W Pool
phase cost. Then scale equal physical capacity to 4/6/8 VCs per port. For six
and eight VCs, compare a conservative one-borrow cap against a fully elastic
upper bound. Pair every point with a private baseline of the same VC count.

The preliminary 171-run matrix finds the crossover around 80--90% direction
bias and shows that VC scaling moves the useful region toward higher injection
rates rather than eliminating it. Detailed results and caveats are in
`xbiased_scaling_results.md`.

## Statistical method and presentation figures

- Use identical seeds for paired mode comparisons.
- Report mean and 95% confidence interval across at least five seeds.
- Never average latency across deadlocked or non-draining runs; mark those
  points explicitly.
- Use network latency below saturation and delivered throughput at saturation.
  Total latency above saturation is dominated by source queuing and should not
  be presented alone.
- Keep raw CSV, exact command line, git commit, and a log for every failed run.

Recommended pre figures:

1. Single-router storage and phase-RR structure diagram.
2. Credit lifecycle state diagram: owned-free -> busy -> returned -> keep or
   handoff, plus idle-peer on-demand reclaim.
3. Throughput/latency curves for uniform and tornado at L=1 and L=8.
4. Policy bar chart at the tornado saturation knee with directional credit
   allocation stacked bars.
5. Cap 2/3/4 tradeoff plot.
6. Dynamic-reversal timeline showing ownership recovery.

## Preliminary 3,000-cycle validation (seed 1)

This is a smoke study, not the final evaluation. It contains 120 points: four
modes, three representative patterns, five injection rates, and two link
latencies. All points completed without deadlock and all Pool read conflicts
were zero.

The subsequent 10,000-cycle, three-seed policy and owner-cap results are
summarized in `preliminary_results.md`; those results should be used for slides
in preference to this shorter smoke table.

The implemented 192-run dynamic E/W reversal matrix and the 48-run recovery
rerun are summarized in `reversal_results.md`. In the current zero-delay owner
table, pressure completes every reclaimable ownership request in the same
cycle. The experiment nevertheless shows a 7.8% latency penalty at epoch 16,
where credit movement is most frequent, motivating a hysteresis/cooldown
ablation and an explicit owner-grant delay model.

At injection 0.9, values below are relative to the equal-capacity private-v4
baseline:

| Pattern | Link latency | Mode | Throughput | Network latency |
|---|---:|---|---:|---:|
| uniform | 1 | pressure | 0.999x | 1.196x |
| uniform | 8 | pressure | 1.000x | 1.032x |
| x-opposite | 1 | pressure | 0.999x | 1.262x |
| x-opposite | 8 | pressure | 0.999x | 1.154x |
| tornado | 1 | pressure | 0.999x | 1.249x |
| tornado | 8 | pressure | 1.001x | **0.952x** |
| tornado | 1 | owner-RR | **0.703x** | **3.022x** |
| tornado | 8 | owner-RR | **0.443x** | **3.062x** |

The initial interpretation is precise but limited:

- **Advantage:** with a long credit round trip and one-sided tornado traffic,
  pressure borrowing lowers in-network latency by about 4.8% while preserving
  throughput. It is using otherwise idle directional capacity.
- **Disadvantage:** with short links or balanced/tie-heavy traffic, the
  complementary bank schedule adds arbitration delay and there is little idle
  capacity worth borrowing.
- **Policy result:** traffic-oblivious owner-RR is unsafe as the main policy.
  It can give credits to the inactive direction and cannot reclaim an idle peer
  credit on demand. Pressure+sticky avoids the observed collapse.

Longer multi-seed runs and the cap/dynamic-reversal experiments are required
before making final performance claims.
