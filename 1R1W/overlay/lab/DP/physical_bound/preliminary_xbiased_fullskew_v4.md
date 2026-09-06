# DP-Phys sweep summary

Input: `lab/DP/physical_bound/results_xbiased_fullskew_v4.csv` (45 runs)

## Validation

| Check | Result |
|---|---:|
| deadlock-free runs | PASS |
| zero Pool read conflicts | PASS |
| allocation conservation | PASS |
| migration conservation | PASS |
| read/return conservation | PASS |
| directional allocation sum | PASS |
| ownership waits do not over-complete | PASS |

## Summary at injection rate 0.1

Values are mean +/- approximate 95% CI across seeds. Ratios are paired against private_v4 with the same seed.

| Pattern | Torus | L | VCs | Epoch | X bias | Hops | Mode | Throughput | vs base | Network latency | vs base | Reclaim % | Handoff % | Pool service % | Wait complete % | Recovery mean/max | Dominant Pool allocation |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 1.0 | 3 | dpphys_pressure | 0.0496 +/- 0.0004 | 1.818 +/- 0.061 | 50.30 +/- 0.24 | 0.280 +/- 0.012 | 1.79 +/- 0.14 | 1.68 +/- 0.14 | 54.62 +/- 0.07 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | west (100.0%) |
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 1.0 | 3 | dpphys_pressure_cap4 | 0.0496 +/- 0.0004 | 1.818 +/- 0.062 | 47.70 +/- 0.06 | 0.265 +/- 0.012 | 0.80 +/- 0.05 | 0.60 +/- 0.05 | 63.25 +/- 0.09 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | west (100.0%) |
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 1.0 | 3 | private_v4 | 0.0273 +/- 0.0008 | n/a | 180.14 +/- 8.17 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
