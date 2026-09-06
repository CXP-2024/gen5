# DP-Phys sweep summary

Input: `lab/DP/physical_bound/results_reversal_recovery_v4.csv` (48 runs)

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

## Summary at injection rate 0.9

Values are mean +/- approximate 95% CI across seeds. Ratios are paired against private_v4 with the same seed.

| Pattern | L | Epoch | Mode | Throughput | vs base | Network latency | vs base | Reclaim % | Handoff % | Pool service % | Wait complete % | Recovery mean/max | Dominant Pool allocation |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| torus3d_x_reversal | 8 | 16 | dpphys_owner_rr | 0.1531 +/- 0.0007 | 0.982 +/- 0.002 | 30.35 +/- 0.60 | 1.065 +/- 0.010 | 0.00 +/- 0.00 | 35.60 +/- 1.18 | 44.39 +/- 0.60 | n/a | n/a | west (50.1%) |
| torus3d_x_reversal | 8 | 16 | dpphys_pressure | 0.1559 +/- 0.0004 | 0.999 +/- 0.001 | 30.72 +/- 0.65 | 1.078 +/- 0.011 | 18.99 +/- 1.85 | 8.06 +/- 1.06 | 60.31 +/- 0.42 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | west (50.3%) |
| torus3d_x_reversal | 8 | 16 | dpphys_rts | 0.1557 +/- 0.0004 | 0.998 +/- 0.000 | 29.11 +/- 0.36 | 1.022 +/- 0.003 | 0.00 +/- 0.00 | 0.00 +/- 0.00 | 56.81 +/- 0.38 | n/a | n/a | west (50.2%) |
| torus3d_x_reversal | 8 | 16 | private_v4 | 0.1560 +/- 0.0004 | n/a | 28.49 +/- 0.35 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| torus3d_x_reversal | 8 | 256 | dpphys_owner_rr | 0.1543 +/- 0.0005 | 0.986 +/- 0.004 | 29.23 +/- 0.19 | 1.098 +/- 0.012 | 0.00 +/- 0.00 | 4.60 +/- 0.70 | 30.14 +/- 0.23 | n/a | n/a | west (55.2%) |
| torus3d_x_reversal | 8 | 256 | dpphys_pressure | 0.1567 +/- 0.0005 | 1.002 +/- 0.001 | 27.26 +/- 0.36 | 1.024 +/- 0.002 | 2.42 +/- 1.05 | 1.23 +/- 0.52 | 66.12 +/- 0.04 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | west (56.1%) |
| torus3d_x_reversal | 8 | 256 | dpphys_rts | 0.1565 +/- 0.0006 | 1.000 +/- 0.001 | 27.20 +/- 0.28 | 1.022 +/- 0.003 | 0.00 +/- 0.00 | 0.00 +/- 0.00 | 64.01 +/- 0.58 | n/a | n/a | west (56.1%) |
| torus3d_x_reversal | 8 | 256 | private_v4 | 0.1565 +/- 0.0008 | n/a | 26.63 +/- 0.36 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| torus3d_x_reversal | 8 | 4 | dpphys_owner_rr | 0.1575 +/- 0.0000 | 1.000 +/- 0.000 | 28.01 +/- 0.01 | 1.024 +/- 0.001 | 0.00 +/- 0.00 | 50.21 +/- 0.23 | 51.27 +/- 0.16 | n/a | n/a | east (50.0%) |
| torus3d_x_reversal | 8 | 4 | dpphys_pressure | 0.1575 +/- 0.0000 | 1.000 +/- 0.000 | 27.97 +/- 0.03 | 1.022 +/- 0.001 | 4.79 +/- 0.21 | 5.23 +/- 0.38 | 52.56 +/- 0.54 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | west (50.1%) |
| torus3d_x_reversal | 8 | 4 | dpphys_rts | 0.1575 +/- 0.0000 | 1.000 +/- 0.000 | 27.97 +/- 0.03 | 1.022 +/- 0.001 | 0.00 +/- 0.00 | 0.00 +/- 0.00 | 52.61 +/- 0.42 | n/a | n/a | west (50.1%) |
| torus3d_x_reversal | 8 | 4 | private_v4 | 0.1575 +/- 0.0000 | n/a | 27.37 +/- 0.02 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| torus3d_x_reversal | 8 | 64 | dpphys_owner_rr | 0.1540 +/- 0.0006 | 0.994 +/- 0.010 | 29.41 +/- 0.30 | 1.059 +/- 0.026 | 0.00 +/- 0.00 | 12.37 +/- 0.90 | 32.81 +/- 0.32 | n/a | n/a | west (51.3%) |
| torus3d_x_reversal | 8 | 64 | dpphys_pressure | 0.1558 +/- 0.0011 | 1.006 +/- 0.005 | 28.60 +/- 0.86 | 1.030 +/- 0.009 | 7.93 +/- 2.58 | 3.84 +/- 1.55 | 64.61 +/- 0.28 | 100.00 +/- 0.00 | 0.00 +/- 0.00/0.00 +/- 0.00 | west (51.3%) |
| torus3d_x_reversal | 8 | 64 | dpphys_rts | 0.1553 +/- 0.0015 | 1.002 +/- 0.003 | 28.28 +/- 0.79 | 1.018 +/- 0.007 | 0.00 +/- 0.00 | 0.00 +/- 0.00 | 61.99 +/- 0.09 | n/a | n/a | west (51.3%) |
| torus3d_x_reversal | 8 | 64 | private_v4 | 0.1549 +/- 0.0018 | n/a | 27.77 +/- 0.89 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
