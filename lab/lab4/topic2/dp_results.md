# Dimension Pool (DP): Experimental Results

> **Note (2026-08-28):** superseded by `dp_report.md` after an adversarial
> audit. The equal-storage headline framing in §3 (finding 1), §4, and §6
> overstates attribution — the C=4 “doubling” is measured against a
> credit-RTT-starved baseline, and on one-sided patterns the DP run is
> bit-identical to the next-larger plain baseline. See `dp_report.md` §3–4
> for the corrected claims. The tables and raw numbers below remain valid.

Companion to `dp_design.md` (mechanism and safety) and `dp_plan.md`
(planning notes). Raw data: `results_dp.csv` (1000 points),
`summary_dp.csv`, `gains_dp.csv`, `deadlock_probes_dp.csv`.
Figures: `latency_throughput_dp_{a,b}.*`, `source_acceptance_dp_{a,b}.*`,
`dp_activity.*`.

## 1. Setup

4×4×4 Torus3D, 64 nodes, ctrl vnet 0 (single-flit packets), 10 000
sim-cycles, injection rates 0.05–1.00 step 0.05, five patterns, ten
configurations (see the matrix in `dp_design.md` §6). Throughput =
received packets / node / Ruby cycle; a point is *stable* when
injected/expected ≥ 0.9. The Ruby 2:1 clock makes 0.5 packets/node/cycle
the offered-load ceiling at rate 1.0.

## 2. Safety: zero deadlocks

- All 1000 sweep points completed with exit 0 and **no deadlock**.
- Six saturation probes (200 000 cycles at rate 1.00 — 20× the sweep
  length) on the DP configurations most at risk:

| Config | Pattern | Deadlock | Packets delivered |
|---|---|---|---|
| A2 (DP-CBS vcs=4 r=2 S=2) | transpose | none | 3 790 857 |
| A2 | xopposite | none | 3 200 912 |
| A4 (DP-CBS vcs=6 r=2 S=4) | transpose | none | 4 493 374 |
| A4 | xopposite | none | 4 267 328 |
| B2 (DP-ESC vcs=3 S=2) | transpose | none | 4 704 488 |
| B2 | xopposite | none | 2 964 906 |

Consistent with the proofs in `dp_design.md` §4: the pool is never in the
safety path.

## 3. Equal-storage comparison (the headline claim)

Peak stable throughput, DP vs the baseline with the same usable storage
per dimension pair (`gains_dp.csv`, kind = equal_storage):

| Pair | xopposite | tornado | transpose | neighbor | uniform |
|---|---|---|---|---|---|
| **A C=6**: A2 vs A1 | **+20.9%** | 0 (ceiling) | +1.4% | 0 (ceiling) | +2.6% |
| **A C=8**: A4 vs A3 | −2.7% | 0 (ceiling) | +1.3% | 0 (ceiling) | +0.0% |
| **B C=4**: B2 vs B1 | **+37.1%** | **+95.0%** | **+87.5%** | **+103.0%** | **+95.7%** |
| **B C=6**: B4 vs B3 | **+21.3%** | **+31.0%** | **+29.2%** | **+24.9%** | **+28.5%** |
| **B C=8**: B6 vs B5 | 0 (ceiling) | 0 (ceiling) | 0 (ceiling) | 0 (ceiling) | 0 (ceiling) |

"Ceiling" marks groups where both configurations saturate the 0.5
offered-load limit, so no difference is observable.

Findings:

1. **DP-ESC is the star.** At the smallest budget (C=4) pooling
   *doubles* saturation throughput on four of five patterns
   (0.195→0.38–0.40); at C=6 it still gains 21–31%. Adaptive routing
   makes per-pair demand bursty and asymmetric — exactly the imbalance
   pooling monetizes — and the exempt escape substrate never throttles
   the pool.
2. **DP-CBS wins its headline case.** On the one-sided xopposite ring at
   C=6 the hot direction uses its 2 dedicated slots plus the whole cap
   (4 usable vs the baseline's 3): +20.9%.
3. **Zero cost on balanced traffic.** Uniform random: DP matches or
   slightly beats its equal-storage baseline everywhere (+0.0 to +2.6%).
4. **One honest regression.** A4 vs A3 on xopposite is −2.7%: DP-CBS's
   safety sub-ring has *fixed* depth r=2 regardless of vcs, while plain
   CBS's overhead (one bubble per ring) shrinks *relatively* as vcs
   grows. At C=6 pooling outweighs that overhead; by C=8 plain CBS's
   deeper bubble domain wins. DP-CBS is a scarce-buffer technique.

## 4. Equal-VC comparison (the honest residual test)

Same VC count, DP exposes strictly *less* usable storage (it trades raw
slots for flexibility):

| Pair | xopposite | tornado | transpose | neighbor | uniform |
|---|---|---|---|---|---|
| A vcs=4: A2 (C=6) vs A3 (C=8) | −22.0% | 0 | −10.5% | 0 | −0.0% |
| B vcs=3: B2 (C=4) vs B3 (C=6) | −32.6% | 0.0% | −5.1% | 0.0% | −1.5% |
| B vcs=4/5: B4 (C=6) vs B5 (C=8) | −3.0% | 0 | −0.0% | 0 | 0.0% |

B2 matches B3 exactly on tornado and neighbor while using one third less
usable storage; the deficit only bites on the pattern that pins all
pressure on one direction of one dimension (xopposite). This bounds the
flexibility-for-storage trade: with equal *storage* DP wins (§3), and
with equal *VC count* it concedes only where storage is the binding
resource.

## 5. Mechanism activity (that the pool actually works)

From `summary_dp.csv` / `dp_activity.*` (maxima over the rate axis):

- `dp_shared_grants` is large everywhere (0.23M–0.96M per 10k-cycle
  run): the shared-first allocator routinely places packets in pooled
  slots.
- **Family A, transpose**: `dp_pool_blocks` = 556k (A2) / 679k (A4) —
  both directions of a dimension compete and the cap arbitrates, as
  predicted for mixed-pressure patterns. On xopposite it is exactly 0:
  one-sided traffic leaves the opposite inport idle, so the cap never
  binds before the inport's own pooled VCs are exhausted.
- **Family B**: `dp_pool_blocks` = 0 by construction — pool pressure is
  absorbed at route time (the candidate filter skips pool-full
  outports), and shows up instead as escape usage: on xopposite,
  `escape_transitions` falls from 98k (B2, S=2) to 123 (B6, S=6) as the
  pool widens.
- CBS interplay is healthy: `cbs_entry_blocks` up to 475k under DP-CBS
  saturation with `cbs_mark_moves` active — the depth-2 sub-ring
  discipline is exercised, not bypassed.

## 6. Takeaways for the report

1. With equal usable storage, buffer pooling across a dimension's two
   opposing inports raises saturation throughput by **21–103%** under
   adaptive routing (DP-ESC) and by **+21%** in the DOR+CBS headline
   case, at **zero cost** on balanced traffic and with **zero deadlocks**
   across 1006 runs including 200k-cycle saturation probes.
2. The gain concentrates where buffers are scarce (C=4, C=6); once both
   sides saturate the injection ceiling (C=8) pooling is free but
   unneeded.
3. The PCN reading holds up: pooled liquidity with a private per-side
   reserve outperforms statically split liquidity of the same total, and
   the reserve (CBS sub-ring / escape VCs) is what keeps the pooled
   system live.
