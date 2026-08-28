# Batch 4 — S=1 cap falsification runs (audit)

- **Date:** 2026-08-28 (part of the adversarial audit)
- **Runs:** 18 = 3 cases × 6 rates, 4×4×4 Torus3D, 10 000 cycles.
  Same binaries and harness settings as batch 2, but with
  `--dp-shared-cap=1` (half the pool budget).
- **Data:** `falsification_s1.csv` (extracted from the retained WSL run
  directories `/tmp/audit_*`).

**Purpose:** attribution test — if DP's gain comes from the pooled
budget, halving the cap should destroy it.

| Case | Baseline | DP S=2 | DP S=1 | Reading |
|---|---|---|---|---|
| A2 xopposite | 0.265 | 0.320 | 0.251 | collapses → gain attributable to the pool budget |
| B2 tornado | 0.195 | 0.381 | 0.297 | ~45% of the gain vanishes → budget is a partial contributor |
| B2 neighbor | 0.197 | 0.400 | 0.400 | unchanged, but via escape: 127 878 escape transitions at rate 0.85 vs 0 at S=2 |

The neighbor row is the honest attribution for one-sided B-family
traffic: the gain is a hot-inport lane-count effect (1 → 2 usable
lanes), provided jointly by the pool budget and the escape exemption.

**Validity: VALID** (attribution evidence, not headline numbers).
