# Lab 2 Task 2

This directory contains controlled Garnet parameter sweeps on the 64-node,
8x8 Mesh_XY network. Uniform-random and transpose traffic are used to compare
a distributed workload with a hotspot-prone permutation.

The complete matrix is:

- virtual channels per vnet: 1, 2, 4, and 8;
- router latency: 1, 2, and 4 Ruby cycles;
- link width: 64, 128, and 256 bits for both vnet-0 control packets and
  vnet-2 data packets;
- injection rates: 0.01 through 0.50, for 1,300 total points.

Run or resume the sweep:

```bash
./.venv/bin/python lab/lab2/task2/run_sweep.py
```

Generate all figures and the measured summary:

```bash
./.venv/bin/python lab/lab2/task2/plot_results.py
```

Full gem5 run directories are removed after successful points to limit disk
usage. Logs remain under the ignored `artifacts/logs/` directory. Pass
`--keep-runs` when raw gem5 output directories are required.
