# Batch 1 — CBS sweep (flow control #1)

- **Date:** 2026-08-27
- **Runs:** 240 = 3 modes × 4 patterns × 20 rates (0.05–1.00), 4×4×4
  Torus3D, 10 000 cycles, ctrl vnet 0.
- **Modes:** `torus3d_dor` (algo 3, unprotected), `torus3d_dor_cbs`
  (algo 3 + `--enable-cbs`), `torus3d_adaptive_escape` (algo 4).
- **Patterns:** uniform_random, torus3d_neighbor, torus3d_tornado,
  torus3d_transpose (xopposite did not exist yet).
- **Harness:** `../../run_sweep_topic2.py`, plots via
  `../../plot_results_topic2.py`.

**Key result:** CBS ≡ plain DOR on uniform/neighbor/tornado (zero cost);
on transpose CBS raises max stable throughput 0.224 → 0.258 (+15%) and
cuts latency@0.5 from 340 to 98 cycles. Adaptive+escape still dominates
transpose (routing-level fix). Design doc: `../../cbs_design.md`.

**Validity: VALID.** Baseline batch for flow control #1; also provides
the plain-CBS baselines reused conceptually by family A of the DP sweep.
