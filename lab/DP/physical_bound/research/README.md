# Equal-Physical-Storage Control Study for the Dimension Pool (DP)

**Status: COMPLETE — 1700/1700 runs (PA/PB 1200 + PC 500), 0 deadlocks.
Verdict: interpretation rule 2 fired (see §6).**

## 1. Question

The naive-research sweep compared configurations at *equal usable
occupancy per dimension pair* (`2·dedicated + S`), which lets the DP
configuration carry more physical VCs than its baseline. This study
asks the missing control question:

> With the physical VC count held exactly equal, does the DP cap (a
> pure counter, the only thing DP adds) ever produce an advantage over
> the plain uncapped router?

If yes, the cap has intrinsic value as admission control (a
CBS-style occupancy-restriction effect). If no, DP's measured gains
are attributable to the extra physical lanes plus the comparison
convention, and the honest claim must be restated accordingly.

## 2. What the existing data already says (batch2 re-analysis)

Batch2 (naive-research) contains two equal-physical pairs by accident
of its matrix — same vcs, DP-capped vs plain:

| pair (vcs) | pattern | sat-thr DP | sat-thr plain | Δ% | matched-load latency DP/plain |
|---|---|---|---|---|---|
| A2 vs A3 (4) | xopposite | 0.3202 | 0.4106 | **−22.0** | 9.9 / 9.8 |
| A2 vs A3 (4) | tornado | 0.4989 | 0.4989 | 0.0 (bit-identical) | 11.0 / 11.0 |
| A2 vs A3 (4) | transpose | 0.3008 | 0.3394 | **−11.4** | 15.0 / 12.4 |
| A2 vs A3 (4) | neighbor | 0.4991 | 0.4991 | 0.0 (bit-identical) | 7.0 / 7.0 |
| A2 vs A3 (4) | uniform | 0.4988 | 0.4988 | −0.0 | 12.6 / 12.4 |
| B2 vs B3 (3) | xopposite | 0.2690 | 0.3996 | **−32.7** | 13.6 / 9.7 |
| B2 vs B3 (3) | tornado | 0.3810 | 0.3810 | 0.0 (bit-identical) | 27.8 / 27.8 |
| B2 vs B3 (3) | transpose | 0.3672 | 0.3863 | −4.9 | 27.2 / 14.2 |
| B2 vs B3 (3) | neighbor | 0.3997 | 0.3997 | 0.0 (bit-identical) | 41.0 / 41.0 |
| B2 vs B3 (3) | uniform | 0.3827 | 0.3883 | −1.5 | 25.3 / 19.6 |

At the tight cap used there (S = half the pooled physical slots), the
equal-physical verdict is uniformly tie-or-loss, in both throughput
and matched-load latency. This matches the audit line "equal-VC
deltas up to −32.6% (price of the cap)". What batch2 cannot answer is
whether an *intermediate* cap wins anywhere — it sampled a single cap
value per family.

## 3. New sweep: cap dose-response at fixed hardware

`run_sweep_physical.py`, 4×4×4 Torus3D, ctrl vnet 0, 10 000 cycles,
rates 0.05–1.00 step 0.05, five patterns (xopposite, tornado,
transpose, neighbor, uniform_random). All modes have vcs=4; only the
cap varies:

| Family | Substrate | Pooled/pair | Modes |
|---|---|---|---|
| PA | DOR + CBS (alg 3, r=2) | 4 | plain, S = 1, 2, 3, 4 |
| PB | adaptive + escape (alg 4, esc=1) | 6 | plain, S = 1, 2, 3, 4, 5, 6 |

12 modes × 5 patterns × 20 rates = 1200 runs.

Anchors built into the matrix:

- **PB6 (S=6)**: cap can never bind and DP's shared-first allocation
  order coincides with plain scanning order in the ESC layout, so
  PB6 ≡ PB0 bit-identically is a purity check on the DP code path.
- **PA4 (S=4)**: cap never binds but DP-CBS's shared-first order
  (pooled window [2,4) before dedicated [0,2)) differs from plain's
  [0,4) scan — this cell isolates the allocation-order effect alone.
- **S = 1 cells**: maximum-throttle floor of the dose-response curve.

Metrics: saturation throughput (max reception rate over the rate
sweep) per mode × pattern; packet latency at the highest rate all
modes of a family fully accept; deadlock count (must be 0).

Analysis: `analyze_physical.py` → `summary_physical.csv`.

## 4. Results

1200/1200 runs, **0 deadlocks**. Full data `results_physical.csv`,
digest `summary_physical.csv` (via `analyze_physical.py`).

### 4.1 PB family (adaptive + escape, vcs=4, pooled 6/pair)

Saturation throughput, Δ% vs plain PB0:

| pattern | S=1 | S=2 | S=3 | S=4 | S=5 | S=6 |
|---|---|---|---|---|---|---|
| xopposite | −54.7 | −37.3 | −17.7 | −0.3 | −0.0 | +0.0 |
| tornado | −44.1 | −6.7 | +0.0 | +0.0 | +0.0 | +0.0 |
| transpose | −60.1 | −25.6 | −0.1 | −0.0 | +0.0 | +0.0 |
| neighbor | −0.0 | +0.0 | +0.0 | +0.0 | +0.0 | +0.0 |
| uniform | −55.0 | −15.0 | −0.0 | +0.0 | +0.0 | +0.0 |

Monotone dose-response: tighter cap → worse or equal, **no cell above
plain**. Matched-load latency: S=1 worse, S≥2 ties plain everywhere.
**Anchor PB6 ≡ PB0 bit-identical across all 100 rate-points ✓**
(DP code path has no side effect beyond the cap in the ESC layout).

**Validity caveat:** plain PB0 sits at the 0.5 injection ceiling on
all five patterns, so in this family a capped mode could at best tie —
"beating plain" was impossible by construction. Informative for the
no-harm direction only; the win question moves to PA (headroom on 2
patterns) and the PC supplement (headroom on 4 patterns).

### 4.2 PA family (DOR + CBS, vcs=4, pooled 4/pair)

Saturation throughput, Δ% vs plain PA0:

| pattern | S=1 | S=2 | S=3 | S=4 |
|---|---|---|---|---|
| xopposite | −35.4 | −22.0 | −22.0 | −22.0 |
| tornado | +0.0 | +0.0 | +0.0 | +0.0 |
| transpose | −23.5 | −11.4 | −2.6 | −3.9 |
| neighbor | +0.0 | +0.0 | +0.0 | +0.0 |
| uniform | −1.4 | −0.0 | +0.0 | +0.0 |

Here plain saturates **below** the ceiling on xopposite (0.4106) and
transpose (0.3394) — real headroom existed, and no cap won any cell.

**Decomposition finding (PA4 anchor):** PA4's cap never binds
(S = 4 = pooled max), yet it still loses −22.0% on xopposite —
identical to S=2 and S=3 (all three saturate at exactly 0.3202). The
PA losses are therefore **not cap costs** but the cost of DP-CBS's
substrate restructuring itself: confining the CBS bubble discipline to
the depth-2 dedicated sub-ring (entry needs 2 free of 2 dedicated
slots) is strictly tighter than plain CBS's full-depth-4 discipline
(2 free of 4). Only S=1 adds a genuine cap cost on top.

### 4.3 PC family (adaptive + escape, vcs=3, pooled 4/pair)

The decisive headroom test: plain PC0 saturates **below** the 0.5
injection ceiling on all five patterns (0.3810–0.3997), so a capped
mode had genuine room to beat plain on every single cell — and none
did.

Saturation throughput, Δ% vs plain PC0:

| pattern | S=1 | S=2 | S=3 | S=4 |
|---|---|---|---|---|
| xopposite | −45.8 | −32.7 | −0.6 | +0.0 |
| tornado | −21.6 | +0.0 | +0.0 | +0.0 |
| transpose | −48.4 | −4.9 | −0.2 | +0.0 |
| neighbor | +0.0 | +0.0 | +0.0 | +0.0 |
| uniform | −35.9 | −1.5 | −0.1 | +0.0 |

Monotone dose-response again: tighter cap → worse or equal, best case
is an exact tie at the never-binding cap. Matched-load latency: S=1
worse on every pattern (e.g. tornado 19.3 vs 12.8 at rate 0.60),
S≥2 ties or near-ties plain. **Anchor PC4 ≡ PC0 bit-identical across
all 100 rate-points ✓** (DP purity confirmed at vcs=3 as well).

## 6. Verdict

Interpretation rule 2 (fixed in §5 before the data) fired, and the PC
family removes the PB ceiling caveat: with real headroom on every
pattern, no cap value beats the same-hardware plain router anywhere —
not in saturation throughput and not in matched-load latency. Across
all three substrates the dose-response is monotone (tighter cap →
worse or equal), and the never-binding caps tie plain exactly
(PB6 ≡ PB0 and PC4 ≡ PC0 bit-identical). The PA losses at S ≥ 2 were
separately shown (§4.2) to be substrate-restructuring costs of DP-CBS,
not cap costs.

Conclusion: **the DP cap is a pure counter with zero intrinsic
equal-physical value as admission control in this testbed.** DP's
naive-research gains are entirely a property of the equal-commitment
comparison convention. Any honest claim must be framed as "a floating
split of a fixed permission budget" — a flow-control *policy* result
that lives in domains where the permission token itself is the
provisioned scarce resource (credit/tag/tracker-bound interfaces; see
`iface_digest.txt`) — never as a hardware-efficiency result.

## 5. Interpretation rules (fixed before seeing the data)

To keep ourselves honest, the possible outcomes and their readings,
written down in advance:

1. Some intermediate cap beats plain on some pattern's saturation
   throughput by a reproducible margin → the counter has intrinsic
   equal-physical value as admission control; report the winning
   (pattern, S) cells and the size of the effect.
2. All capped cells ≤ plain everywhere → the cap is pure overhead at
   equal hardware; DP's naive-research gains are then entirely a
   property of the equal-commitment comparison convention, and any
   claim must be framed as "floating split of a fixed permission
   budget" (policy result), never as a hardware-efficiency result.
3. PB6 ≢ PB0 → DP code path has a side effect beyond the cap;
   investigate before trusting anything else in the sweep.
