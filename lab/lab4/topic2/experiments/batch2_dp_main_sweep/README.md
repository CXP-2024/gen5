# Batch 2 — DP main sweep (flow control #2)

- **Date:** 2026-08-27→28 (overnight)
- **Runs:** 1000 = 10 modes × 5 patterns × 20 rates (0.05–1.00), 4×4×4
  Torus3D, 10 000 cycles, ctrl vnet 0. Zero deadlocks.
- **Modes:** equal-storage families A (DOR+CBS substrate) and
  B (adaptive+escape substrate); see the matrix in `../../dp_report.md` §2.
- **Harness:** `../../run_sweep_dp.py`, digests via
  `../../plot_results_dp.py` (writes `summary_dp.csv`, `gains_dp.csv`).

**Canonical interpretation: `../../dp_report.md` (post-audit).**
Cell-level validity (audited 2026-08-28):

- **Citable gains:** B family C=6 (+21–31%, mostly lower bounds);
  A family C=6 xopposite +20.9% (S=1-confirmed attribution).
- **Boundary/negative results (also citable):** A C=8 xopposite −2.7%;
  equal-VC deltas up to −32.6% (price of the cap); uniform ≈ 0
  (no-harm bound).
- **Not citable as flow-control gains:** B C=4 +95–103% (baseline B1 is
  credit-RTT-starved; B2 ≡ B3 bit-identical on one-sided patterns —
  correct claim is budget efficiency "C=4 does C=6's work").
- **No information:** 15/25 equal-storage cells where both sides sit at
  the 0.5 injection ceiling (all of B C=8, tornado/neighbor of A).
- **Instrumentation caveat:** `dp_pool_blocks` ≡ 0 in family B by
  construction (route-time filter uncounted); use `escape_transitions`.
