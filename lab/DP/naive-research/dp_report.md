# Dimension Pool (DP) — Experiment Report

Lab 4, Topic 2, flow control #2. This is the concise, post-audit report;
where it conflicts with the earlier `dp_results.md`, this document wins.
Mechanism and safety proofs: `dp_design.md`. Raw data: `results_dp.csv`
(1000 runs), `gains_dp.csv`, `deadlock_probes_dp.csv`. Figures:
`latency_throughput_dp_{a,b}`, `source_acceptance_dp_{a,b}`, `dp_activity`.

## 1. Mechanism in one paragraph

At each router, the two opposing inports of a dimension (E+W, N+S, U+D)
share their pooled VCs under a joint occupancy cap `S`: a temporarily hot
direction may occupy up to `S` slots of the pair budget while the opposite
side is idle. Deadlock freedom is delegated to a substrate that is never
pooled — a CBS-disciplined dedicated sub-ring of depth `r` (DP-CBS, on DOR)
or exempt escape VCs (DP-ESC, on adaptive routing) — so pooled admission may
fail at any time without risking deadlock.

## 2. Setup

4×4×4 Torus3D, 64 nodes, single-flit control packets (1 packet per VC),
10 000 cycles, injection rates 0.05–1.00 (step 0.05), five patterns
(xopposite, tornado, transpose, neighbor, uniform random). Throughput =
received packets/node/cycle; a point is *stable* when ≥ 90% of the offered
load is accepted; the offered-load ceiling is 0.5.

Each DP configuration is compared with the plain baseline of **equal usable
storage per dimension pair** `C = 2·dedicated + S` (pair-level occupancy
budget; DP carries more physical VCs, whose per-inport concentration is
exactly the mechanism under test):

| Group | Baseline | DP configuration | C |
|---|---|---|---|
| A (DOR+CBS) | A1: vcs=3 | A2: vcs=4, r=2, S=2 | 6 |
| | A3: vcs=4 | A4: vcs=6, r=2, S=4 | 8 |
| B (adaptive+escape) | B1: vcs=2 | B2: vcs=3, S=2 | 4 |
| | B3: vcs=3 | B4: vcs=5, S=4 | 6 |
| | B5: vcs=4 | B6: vcs=7, S=6 | 8 |

## 3. Results

Peak stable throughput gain of DP over its equal-storage baseline.
“ceil” = both sides saturate the 0.5 injection ceiling (no information);
“≥” = the DP side is at the ceiling, so the gain is a lower bound.

| Pair | xopposite | tornado | transpose | neighbor | uniform |
|---|---|---|---|---|---|
| A, C=6 | **+20.9%** | ceil | +1.4% | ceil | ≥+2.6% |
| A, C=8 | −2.7% | ceil | +1.3% | ceil | ceil |
| B, C=4 | +37.1% | +95.0% | +87.5% | +103.0% | +95.7% |
| B, C=6 | **+21.3%** | ≥+31.0% | ≥+29.2% | ≥+24.9% | ≥+28.5% |
| B, C=8 | ceil | ceil | ceil | ceil | ceil |

**Representative numbers.**

1. **DP-ESC, C=6: +21–31% on every pattern** (mostly lower bounds). This
   is the headline claim: a healthy baseline, no ceiling excuse on the
   xopposite cell, uniform-random included.
2. **DP-ESC, C=4 is a budget-efficiency result, not a ×2 flow-control
   result.** On one-sided patterns B2 is bit-identical to plain vcs=3 (B3)
   at every rate: pooling lets a 4-slot pair budget do the work of a plain
   6-slot design. The raw +95–103% over B1 overstates the mechanism,
   because B1 is credit-RTT-starved: with one usable lane per inport and a
   ~5-cycle VC turnaround it saturates at ~0.195 on *all five* patterns
   (family-B peaks track ≈ 0.2 × usable hot-inport lanes, capped at 0.5).
3. **DP-CBS: one clean win, honestly bounded.** xopposite +20.9% at C=6;
   ≥+2.6% (zero cost) on uniform; **−2.7%** at C=8 on xopposite — the fixed
   depth-2 safety sub-ring stops paying off once buffers are plentiful, so
   DP-CBS is a scarce-buffer technique.
4. **The cap has a price under two-sided load.** At equal VC count the
   budget cap costs up to −32.6% (B2 vs B3 on xopposite): equal-storage
   flexibility is bought with contention on the shared budget.

## 4. Attribution and validation

- **Zero deadlocks** in all 1006 runs, including six 200 000-cycle
  saturation probes at rate 1.0 (`deadlock_probes_dp.csv`).
- **Baseline purity**: the post-DP binary reproduces the pre-DP sweep’s
  baseline results bit-identically (160/160 shared rate points), so no gain
  comes from accidental changes to the baseline code paths.
- **Cap falsification (S=1 reruns)** — cut the pool budget in half and see
  whether the gain survives:

| Case | Baseline | DP S=2 | DP S=1 | Reading |
|---|---|---|---|---|
| A2, xopposite | 0.265 | 0.320 | 0.251 | collapses → gain attributable to the pooled budget |
| B2, tornado | 0.195 | 0.381 | 0.297 | ~45% of the gain vanishes → budget is a partial contributor |
| B2, neighbor | 0.197 | 0.400 | 0.400 | unchanged, but via escape: 128k escape transitions vs 0 at S=2 |

  The neighbor case shows the honest attribution for one-sided B-family
  traffic: the gain is a **hot-inport lane-count effect** (1 → 2 usable
  lanes), provided jointly by the pool budget and the escape exemption —
  not by “borrowing idle storage” alone.

## 5. Caveats

- **Shallow-VC substrate.** With 1 flit per VC, per-lane throughput is
  bounded by the credit round trip (~0.2 pkts/cycle/lane), which amplifies
  the value of every extra usable hot-side slot. Deeper VCs would shrink
  the magnitudes; the direction of the effect stands.
- **`dp_pool_blocks` is blind in family B**: pool pressure is absorbed by
  the routing-time candidate filter, which has no counter. Use
  `escape_transitions` to observe it instead.
- Half of the equal-storage table (15/25 cells) sits at the injection
  ceiling; those cells say nothing about relative headroom.

Reproduce with `run_sweep_dp.py` (sweep + CSV) and `plot_results_dp.py`
(figures and gain tables).
