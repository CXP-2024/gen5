# XYZ Global Pool Experiment

## Setup

- Topology: `4x4x4` Torus3D, 64 routers
- Routing: adaptive Torus3D with one independent Mesh3D XYZ escape VC
- Traffic: uniform random, tornado, transpose, x-opposite, neighbor
- Injection rates: `0.05` through `0.50` in steps of `0.05`
- Simulation length: `10000` cycles per point
- Configurations: B2 (`vcs=3`, pooled cap 2 per dimension), B4 (`vcs=5`, cap 4), B6 (`vcs=7`, cap 6)
- Global mode uses caps 6, 12, and 18 respectively, preserving total pooled capacity.
  Because Garnet input buffers own their VCs locally, the global-mode runner
  gives each direction three times as many candidate adaptive VCs and enforces
  the router-wide cap. This is the simulator abstraction that lets a hot
  direction consume capacity otherwise idle in the other two dimensions.

Escape VCs remain independent in both modes. Only adaptive pooled VCs change scope.

## Summary

The values below average all ten injection rates. Throughput is in packets/node/cycle; latency is in cycles.

| Config | Pattern | Per-dim throughput | Global throughput | Delta | Per-dim latency | Global latency | Delta |
|---|---|---:|---:|---:|---:|---:|---:|
| B2 | uniform_random | 0.137134 | 0.137137 | +0.00% | 11.500 | 11.395 | -0.91% |
| B2 | tornado | 0.136936 | 0.136936 | +0.00% | 11.423 | 11.423 | +0.00% |
| B2 | transpose | 0.136938 | 0.136939 | +0.00% | 11.435 | 11.314 | -1.06% |
| B2 | x-opposite | 0.136964 | 0.136972 | +0.01% | 9.886 | 9.274 | -6.18% |
| B2 | neighbor | 0.137001 | 0.137001 | +0.00% | 7.121 | 7.121 | +0.00% |
| B4 | all patterns | approximately 0.137 | approximately 0.137 | approximately 0% | nearly identical | nearly identical | approximately 0% |
| B6 | all patterns | approximately 0.137 | approximately 0.137 | approximately 0% | nearly identical | nearly identical | approximately 0% |

The per-point data is in `summary_global_vs_dimension.csv`; raw results are in
`results_per_dimension_full.csv` and `results_global_full.csv`.

## Conclusion

No point deadlocked, and both modes reached the same throughput ceiling of about
`0.249 packets/node/cycle` at high offered load. More importantly, the DP pool
blocking counter was zero for every point. Consequently, this experiment does
not demonstrate a measurable global-pool advantage: the pool was not the active
bottleneck under these control-traffic settings. The global design is therefore
functionally correct and preserves the independent escape path, but a stronger
claim requires a stress workload that creates directional imbalance and enough
control-VC occupancy to make `dp_pool_blocks` nonzero.

Recommended follow-up: run longer simulations with a higher control-packet
fraction or a directional hotspot, and report pool occupancy/blocking together
with throughput and tail latency.

## True Global-Capacity Rerun

The initial comparison only merged the occupancy counter; local input ports
still had too few adaptive VCs to borrow capacity. The corrected global runner
allocates three times as many candidate adaptive VCs per input direction and
uses the router-wide cap as the effective capacity. The full corrected results
are in `summary_true_global.csv`.

| Config | Pattern | Per-dimension peak | True global peak | Gain |
|---|---|---:|---:|---:|
| B2 (cap 2/pair vs global cap 6) | x-opposite | 0.268981 | 0.498980 | +85.51% |
| B2 | tornado | 0.380664 | 0.474095 | +24.54% |
| B2 | transpose | 0.366658 | 0.448933 | +22.44% |
| B2 | uniform random | 0.382392 | 0.473794 | +23.90% |
| B2 | neighbor | 0.399602 | 0.499080 | +24.89% |
| B4 (cap 4/pair vs global cap 12) | x-opposite | 0.484047 | 0.498980 | +3.08% |
| B4 | other patterns | approximately unchanged | approximately unchanged | approximately 0% |
| B6 (cap 6/pair vs global cap 18) | all patterns | approximately unchanged | approximately unchanged | approximately 0% |

All 300 points in each corrected sweep completed without deadlock. The large
B2 gains occur because each dimension-pair pool has only two adaptive slots;
the true global pool lets a directional hotspot use the six-slot router-wide
budget. Once the independent pools are already large enough (B4/B6), the
network reaches the injection ceiling and global sharing has little remaining
headroom to improve.
