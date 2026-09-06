# DP-Phys sweep summary

Input: `lab/DP/physical_bound/results_cap_v4.csv` (72 runs)

## Validation

| Check | Result |
|---|---:|
| deadlock-free runs | PASS |
| zero Pool read conflicts | PASS |
| allocation conservation | PASS |
| migration conservation | PASS |
| read/return conservation | PASS |
| directional allocation sum | PASS |

## Summary at injection rate 0.9

Values are mean +/- approximate 95% CI across seeds. Ratios are paired against private_v4 with the same seed.

| Pattern | L | Mode | Throughput | vs base | Network latency | vs base | Reclaim % | Handoff % | Pool service % | Dominant Pool allocation |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| torus3d_tornado | 8 | dpphys_pressure | 0.1563 +/- 0.0000 | 1.000 +/- 0.000 | 46.97 +/- 0.03 | 0.952 +/- 0.002 | 0.49 +/- 0.02 | 0.40 +/- 0.02 | 66.38 +/- 0.08 | down (33.4%) |
| torus3d_tornado | 8 | dpphys_pressure_cap2 | 0.1554 +/- 0.0000 | 0.994 +/- 0.000 | 58.25 +/- 0.05 | 1.180 +/- 0.001 | 0.00 +/- 0.00 | 0.00 +/- 0.00 | 51.35 +/- 0.01 | west (33.5%) |
| torus3d_tornado | 8 | dpphys_pressure_cap4 | 0.1564 +/- 0.0000 | 1.000 +/- 0.000 | 46.47 +/- 0.04 | 0.941 +/- 0.000 | 0.19 +/- 0.01 | 0.01 +/- 0.01 | 69.65 +/- 0.10 | down (33.4%) |
| torus3d_tornado | 8 | private_v4 | 0.1564 +/- 0.0000 | n/a | 49.37 +/- 0.07 | n/a | n/a | n/a | n/a | n/a |
| uniform_random | 8 | dpphys_pressure | 0.1565 +/- 0.0000 | 1.001 +/- 0.000 | 49.87 +/- 0.11 | 1.032 +/- 0.000 | 13.99 +/- 0.06 | 5.31 +/- 0.05 | 52.41 +/- 0.07 | up (16.8%) |
| uniform_random | 8 | dpphys_pressure_cap2 | 0.1565 +/- 0.0000 | 1.000 +/- 0.000 | 50.56 +/- 0.13 | 1.046 +/- 0.001 | 0.00 +/- 0.00 | 0.00 +/- 0.00 | 48.50 +/- 0.04 | east (16.7%) |
| uniform_random | 8 | dpphys_pressure_cap4 | 0.1565 +/- 0.0000 | 1.001 +/- 0.000 | 49.81 +/- 0.12 | 1.031 +/- 0.000 | 14.12 +/- 0.15 | 6.28 +/- 0.11 | 52.61 +/- 0.04 | north (16.8%) |
| uniform_random | 8 | private_v4 | 0.1564 +/- 0.0000 | n/a | 48.32 +/- 0.11 | n/a | n/a | n/a | n/a | n/a |
