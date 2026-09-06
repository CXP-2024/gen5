# DP-Phys sweep summary

Input: `lab/DP/physical_bound/results_xbiased_vcscale.csv` (72 runs)

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

## Summary at injection rate 0.2

Values are mean +/- approximate 95% CI across seeds. Ratios are paired against private_v4 with the same seed.

| Pattern | Torus | L | VCs | Epoch | X bias | Hops | Mode | Throughput | vs base | Network latency | vs base | Reclaim % | Handoff % | Pool service % | Wait complete % | Recovery mean/max | Dominant Pool allocation |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| torus3d_xbiased | 8x4x4 | 8 | 6 | 0 | 1.0 | 3 | dpphys_pressure_v6 | 0.0193 +/- 0.0006 | 1.014 +/- 0.024 | 377.04 +/- 13.38 | 0.791 +/- 0.022 | 1.55 +/- 0.22 | 1.02 +/- 0.26 | 25.00 +/- 0.89 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | west (100.0%) |
| torus3d_xbiased | 8x4x4 | 8 | 6 | 0 | 1.0 | 3 | dpphys_pressure_v6_full | 0.0989 +/- 0.0008 | 5.206 +/- 0.017 | 49.10 +/- 0.54 | 0.103 +/- 0.000 | 1.48 +/- 0.01 | 1.32 +/- 0.01 | 60.51 +/- 0.12 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | west (100.0%) |
| torus3d_xbiased | 8x4x4 | 8 | 6 | 0 | 1.0 | 3 | private_v6 | 0.0190 +/- 0.0002 | n/a | 476.66 +/- 4.81 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| torus3d_xbiased | 8x4x4 | 8 | 8 | 0 | 1.0 | 3 | dpphys_pressure_v8 | 0.0993 +/- 0.0003 | 1.080 +/- 0.082 | 48.29 +/- 0.03 | 0.851 +/- 0.171 | 1.19 +/- 0.07 | 1.12 +/- 0.07 | 46.80 +/- 0.05 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | west (100.0%) |
| torus3d_xbiased | 8x4x4 | 8 | 8 | 0 | 1.0 | 3 | dpphys_pressure_v8_full | 0.0993 +/- 0.0003 | 1.080 +/- 0.082 | 47.06 +/- 0.01 | 0.830 +/- 0.166 | 0.32 +/- 0.00 | 0.07 +/- 0.00 | 52.85 +/- 0.07 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | west (100.0%) |
| torus3d_xbiased | 8x4x4 | 8 | 8 | 0 | 1.0 | 3 | private_v8 | 0.0923 +/- 0.0074 | n/a | 57.85 +/- 10.88 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
