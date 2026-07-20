# Lab 3 Task 1

This directory contains the reproducible 16-node Ring experiment and a 4x4
Mesh baseline. Both use uniform-random, single-flit control traffic for 10,000
Ruby cycles at injection rates 0.01 through 0.50.

Run or resume all 100 points:

```bash
./.venv/bin/python lab/lab3/task1/run_sweep.py
```

Generate the figures and measured analysis:

```bash
./.venv/bin/python lab/lab3/task1/plot_results.py
```

Full gem5 run directories are removed after each successful point. Logs are
retained in the ignored `artifacts/logs/` directory. Use `--keep-runs` to keep
all raw gem5 output directories.
