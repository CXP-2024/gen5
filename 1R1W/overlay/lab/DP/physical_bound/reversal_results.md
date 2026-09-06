# DP-Phys dynamic E/W reversal experiment

## Purpose

This experiment tests whether Pool credits follow a changing hot direction,
how quickly stranded ownership is recovered, and whether stickiness helps or
hurts when traffic changes faster than the credit loop can settle.

`torus3d_x_reversal` was added to the Garnet synthetic tester. Every source
sends one hop in +X for one epoch and one hop in -X for the next epoch. At the
receiving router this alternates the hot input between West and East. Epochs of
4, 16, 64, and 256 cycles probe changes faster than, comparable to, and slower
than the L=8 link/credit response time.

The full matrix contains 192 runs:

- modes: equal-capacity `private_v4`, `dpphys_rts`, `dpphys_owner_rr`, and
  `dpphys_pressure`;
- injection rates: 0.3 and 0.9;
- link latencies: 1 and 8 cycles;
- epochs: 4, 16, 64, and 256 cycles;
- seeds: 1, 2, and 3; 10,000 simulated cycles per run.

A 48-run L=8, injection-0.9 subset was repeated after adding ownership-demand
episode counters. All runs use one-flit control traffic and a 4x4x4 Torus3D.

## Safety and structural checks

All 192 full-matrix runs and all 48 recovery reruns completed without deadlock.
Every extended-statistics run passed allocation, migration, returned-credit,
and directional-count conservation. Pool read conflicts were zero, as required
by the complementary RES/POOL phase schedule.

The DP-Phys event trace also shows owner changes in both directions and records
whether each change came from an on-demand reclaim or a release-time handoff.
The directional allocation counts stay close to 50/50 over the full run, as
expected from equal-duration +X/-X phases.

## High-load, long-link result

The following values are three-seed means for injection 0.9 and link latency 8.
Latency ratios use the private-v4 run with the same epoch and seed.

| Epoch | Mode | Throughput/base | Network latency | Latency/base | Demand reclaim / Pool allocation | Release handoff / Pool read |
|---:|---|---:|---:|---:|---:|---:|
| 4 | RTS | 1.000 | 27.97 | 1.022 | 0.00% | 0.00% |
| 4 | owner-RR | 1.000 | 28.01 | 1.024 | 0.00% | 50.21% |
| 4 | pressure | 1.000 | 27.97 | 1.022 | 4.79% | 5.23% |
| 16 | RTS | 0.998 | 29.11 | 1.022 | 0.00% | 0.00% |
| 16 | owner-RR | 0.982 | 30.35 | 1.065 | 0.00% | 35.60% |
| 16 | pressure | 0.999 | 30.72 | 1.078 | 18.99% | 8.06% |
| 64 | RTS | 1.002 | 28.28 | 1.018 | 0.00% | 0.00% |
| 64 | owner-RR | 0.994 | 29.41 | 1.059 | 0.00% | 12.37% |
| 64 | pressure | 1.006 | 28.60 | 1.030 | 7.93% | 3.84% |
| 256 | RTS | 1.000 | 27.20 | 1.022 | 0.00% | 0.00% |
| 256 | owner-RR | 0.986 | 29.23 | 1.098 | 0.00% | 4.60% |
| 256 | pressure | 1.002 | 27.26 | 1.024 | 2.42% | 1.23% |

The private-v4 network latencies for epochs 4, 16, 64, and 256 were 27.37,
28.49, 27.77, and 26.63 cycles respectively.

## Credit recovery result

For `dpphys_pressure`, every recorded ownership-demand episode completed in
the same cycle:

```text
completion rate = 100%
mean recovery latency = 0 cycles
maximum recovery latency = 0 cycles
```

This is consistent with the present implementation: if an idle peer-owned Pool
slot exists and the requester is below owner cap 3, pressure performs an
immediate owner-table update before allocating the VC. Thus these numbers
validate the algorithm and establish an optimistic upper bound; they do not
model a physical grant wire. A one-cycle or parameterized owner-grant transport
experiment is still required before making a hardware timing claim.

RTS and owner-RR have no on-demand reclaim path, so an equivalent completed
recovery episode is not observed. Their behavior is instead visible in
release-time credit placement: RTS never hands ownership over, while owner-RR
can churn ownership without regard to demand.

## Interpretation

The reversal experiment exposes a real tradeoff rather than a universal win:

- Pressure successfully moves credits toward the new hot direction, and it
  never leaves a reclaimable idle credit blocked in this test.
- Frequent direction changes make yesterday's sticky owner less useful.
  Epoch 16 causes the most mobility (18.99% on-demand reclaims) and also the
  largest pressure latency penalty (7.8%). This epoch is comparable to the
  long-link pipeline/credit response time, so ownership is repeatedly moved
  while old traffic is still draining.
- Epoch 4 is so fast that the aggregate demand appears nearly balanced. Pooling
  has little stranded capacity to exploit, but still pays about 2.2% latency.
- At epochs 64 and 256, mobility falls to 7.93% and 2.42%; pressure is stable
  again, but this symmetric one-hop workload still offers little net capacity
  advantage over four private VCs.
- Blind owner-RR is not a safe substitute for demand awareness. It hands off
  50.21% of returned credits at epoch 4 and remains the least reliable policy;
  at epoch 256 it raises latency by 9.8% and loses about 1.4% throughput.

The contrast with persistent one-sided tornado traffic is useful for the paper:
at L=8 and injection 0.9, pressure cap 3 previously reduced latency by about
4.8% at equal physical storage. Pooling helps when directional imbalance
persists long enough to reuse borrowed space; it loses when demand is balanced
or changes on the same time scale as ownership and credit circulation.

## Design implication and next ablations

The next policy should keep demand-driven reclaim but avoid reacting to every
short reversal. Two practical variants should be compared against the current
zero-threshold pressure policy:

1. require peer RES pressure for `K` consecutive cycles before a release-time
   handoff, while still allowing an immediate reclaim of an idle credit when
   allocation would otherwise fail;
2. add a one-cycle owner-grant delay and a small ownership-transfer cooldown,
   then sweep `K`/cooldown over 0, 2, 4, and 8 cycles.

The evaluation should then add explicit packet bursts and multi-flit packets.
That will test the original hypothesis that keeping the last user's single
remaining credit is valuable for its next large packet, rather than inferring
packet locality from one-flit traffic.
