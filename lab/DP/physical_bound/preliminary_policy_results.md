# DP-Phys sweep summary

Input: `lab/DP/physical_bound/results_policy_v4.csv` (96 runs)

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
| torus3d_tornado | 1 | dpphys_owner_rr | 0.3138 +/- 0.0013 | 0.699 +/- 0.003 | 32.08 +/- 0.16 | 3.067 +/- 0.016 | 0.00 +/- 0.00 | 0.11 +/- 0.00 | 25.37 +/- 0.28 | west (37.6%) |
| torus3d_tornado | 1 | dpphys_pressure | 0.4488 +/- 0.0003 | 1.000 +/- 0.000 | 13.09 +/- 0.01 | 1.251 +/- 0.001 | 0.13 +/- 0.01 | 0.09 +/- 0.01 | 59.11 +/- 0.00 | down (33.4%) |
| torus3d_tornado | 1 | dpphys_rts | 0.4488 +/- 0.0003 | 1.000 +/- 0.000 | 12.84 +/- 0.01 | 1.227 +/- 0.000 | 0.00 +/- 0.00 | 0.00 +/- 0.00 | 53.45 +/- 0.03 | down (33.4%) |
| torus3d_tornado | 1 | private_v4 | 0.4489 +/- 0.0003 | n/a | 10.46 +/- 0.00 | n/a | n/a | n/a | n/a | n/a |
| torus3d_tornado | 8 | dpphys_owner_rr | 0.0680 +/- 0.0004 | 0.435 +/- 0.003 | 157.03 +/- 1.16 | 3.181 +/- 0.022 | 0.00 +/- 0.00 | 0.44 +/- 0.00 | 27.67 +/- 0.02 | west (45.7%) |
| torus3d_tornado | 8 | dpphys_pressure | 0.1563 +/- 0.0000 | 1.000 +/- 0.000 | 46.97 +/- 0.03 | 0.952 +/- 0.002 | 0.49 +/- 0.02 | 0.40 +/- 0.02 | 66.38 +/- 0.08 | down (33.4%) |
| torus3d_tornado | 8 | dpphys_rts | 0.1554 +/- 0.0000 | 0.994 +/- 0.000 | 58.25 +/- 0.05 | 1.180 +/- 0.001 | 0.00 +/- 0.00 | 0.00 +/- 0.00 | 51.35 +/- 0.01 | west (33.5%) |
| torus3d_tornado | 8 | private_v4 | 0.1564 +/- 0.0000 | n/a | 49.37 +/- 0.07 | n/a | n/a | n/a | n/a | n/a |
