# DP-Phys sweep summary

Input: `lab/DP/physical_bound/results_xbiased_bias_v4.csv` (54 runs)

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
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 0.5 | 3 | dpphys_pressure | 0.0496 +/- 0.0004 | 1.000 +/- 0.000 | 46.94 +/- 0.02 | 1.023 +/- 0.000 | 18.52 +/- 0.18 | 4.11 +/- 0.03 | 50.50 +/- 0.20 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | east (50.1%) |
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 0.5 | 3 | dpphys_pressure_cap4 | 0.0496 +/- 0.0004 | 1.000 +/- 0.000 | 46.68 +/- 0.03 | 1.018 +/- 0.000 | 23.47 +/- 0.22 | 4.66 +/- 0.04 | 52.18 +/- 0.21 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | east (50.1%) |
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 0.5 | 3 | private_v4 | 0.0496 +/- 0.0004 | n/a | 45.86 +/- 0.02 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 0.6 | 3 | dpphys_pressure | 0.0496 +/- 0.0004 | 1.000 +/- 0.000 | 47.09 +/- 0.04 | 1.023 +/- 0.001 | 16.69 +/- 0.24 | 3.71 +/- 0.02 | 50.34 +/- 0.19 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | west (63.3%) |
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 0.6 | 3 | dpphys_pressure_cap4 | 0.0496 +/- 0.0004 | 1.000 +/- 0.000 | 46.76 +/- 0.04 | 1.015 +/- 0.001 | 22.35 +/- 0.30 | 4.35 +/- 0.05 | 52.40 +/- 0.14 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | west (64.1%) |
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 0.6 | 3 | private_v4 | 0.0496 +/- 0.0004 | n/a | 46.05 +/- 0.06 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 0.7 | 3 | dpphys_pressure | 0.0496 +/- 0.0004 | 1.000 +/- 0.000 | 47.39 +/- 0.02 | 1.016 +/- 0.002 | 11.88 +/- 0.21 | 3.12 +/- 0.05 | 50.35 +/- 0.17 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | west (76.0%) |
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 0.7 | 3 | dpphys_pressure_cap4 | 0.0496 +/- 0.0004 | 1.000 +/- 0.000 | 46.87 +/- 0.02 | 1.005 +/- 0.002 | 19.00 +/- 0.32 | 3.62 +/- 0.01 | 53.47 +/- 0.13 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | west (77.3%) |
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 0.7 | 3 | private_v4 | 0.0496 +/- 0.0004 | n/a | 46.65 +/- 0.08 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 0.8 | 3 | dpphys_pressure | 0.0496 +/- 0.0004 | 1.000 +/- 0.000 | 47.93 +/- 0.07 | 1.001 +/- 0.002 | 6.27 +/- 0.12 | 2.42 +/- 0.08 | 50.55 +/- 0.14 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | west (87.6%) |
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 0.8 | 3 | dpphys_pressure_cap4 | 0.0496 +/- 0.0004 | 1.000 +/- 0.000 | 47.02 +/- 0.05 | 0.982 +/- 0.002 | 13.50 +/- 0.31 | 2.66 +/- 0.07 | 55.47 +/- 0.11 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | west (88.7%) |
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 0.8 | 3 | private_v4 | 0.0496 +/- 0.0004 | n/a | 47.91 +/- 0.15 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 0.9 | 3 | dpphys_pressure | 0.0496 +/- 0.0004 | 1.021 +/- 0.028 | 48.78 +/- 0.07 | 0.908 +/- 0.075 | 2.62 +/- 0.09 | 1.98 +/- 0.06 | 51.65 +/- 0.05 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | west (96.3%) |
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 0.9 | 3 | dpphys_pressure_cap4 | 0.0496 +/- 0.0004 | 1.021 +/- 0.028 | 47.29 +/- 0.04 | 0.880 +/- 0.074 | 6.15 +/- 0.29 | 1.58 +/- 0.07 | 58.48 +/- 0.06 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | west (96.7%) |
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 0.9 | 3 | private_v4 | 0.0486 +/- 0.0013 | n/a | 53.94 +/- 4.68 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 1.0 | 3 | dpphys_pressure | 0.0496 +/- 0.0004 | 1.818 +/- 0.061 | 50.30 +/- 0.24 | 0.280 +/- 0.012 | 1.79 +/- 0.14 | 1.68 +/- 0.14 | 54.62 +/- 0.07 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | west (100.0%) |
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 1.0 | 3 | dpphys_pressure_cap4 | 0.0496 +/- 0.0004 | 1.818 +/- 0.062 | 47.70 +/- 0.06 | 0.265 +/- 0.012 | 0.80 +/- 0.05 | 0.60 +/- 0.05 | 63.25 +/- 0.09 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | west (100.0%) |
| torus3d_xbiased | 8x4x4 | 8 | 4 | 0 | 1.0 | 3 | private_v4 | 0.0273 +/- 0.0008 | n/a | 180.14 +/- 8.17 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
