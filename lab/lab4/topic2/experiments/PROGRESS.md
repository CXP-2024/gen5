# Topic 2 — Experiment Progress

Updated 2026-08-28. Canonical interpretation of all numbers: `../dp_report.md`.

## Completed (valid)

| Batch | Content | Key valid result |
|---|---|---|
| 1 | CBS sweep, 240 runs, 4×4×4 | CBS +15% transpose throughput (flow control #1) |
| 2 | DP main sweep, 1000 runs, 10 modes × 5 patterns × 20 rates | **B family C=6: +21–31%** (headline); A C=6 xopposite +20.9%; negatives: A C=8 −2.7%, equal-VC up to −32.6%, uniform ≈ 0 (no-harm) |
| 3 | Saturation deadlock probes, 6 × 200k cycles | 0 deadlocks (safety, empirical leg) |
| 4 | S=1 cap falsification, 18 runs | gains attributable to pool budget (+ escape path on one-sided traffic) |
| 5 | Baseline purity re-runs | 160/160 rate points bit-identical pre/post DP code |

Not citable as gains (recorded in batch 2 README): B C=4 +95–103% (starved baseline), 15/25 injection-ceiling cells.

## Planned

| ID | Experiment | Status |
|---|---|---|
| P1 | Scale sweep: 128 (4×4×8) and 256 (4×8×8) nodes, headline configs (B1/B2/B3 + A2/A3), uniform + tornado + xopposite | capacity limits mapped (see `batch6_scale_probe/README.md`): max feasible = **256 nodes**; needs pow2 dirs, `--mem-size=8GB`, `NUMBER_BITS_PER_SET=256` rebuild. Rebuild + probe running. |
| P2 | Staleness ablation: charge the pool check a k-cycle-old shadow of `m_dp_shared_occ` (k=1,2) | proposed, ~1 h impl + short sweep |
| P3 | Non-cubic torus | merged into P1 (128/256 are non-cubic; transpose pattern unavailable there, other 4 patterns fine) |

Parked (user decision): per-side fairness breakdown; deeper-VC substrates; non-torus topologies (need new code).

## Layout

Each `batchN_*/` holds the raw/summary CSVs plus a README with run
parameters and a per-cell validity verdict. `batch6_scale_probe/` will
receive P1 capacity data.
