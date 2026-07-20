# Lab 3 Task 2

This directory compares three ways to provide 16 control-buffer slots per
input/output path on the 16-node Ring:

- `VC=1, depth=1`;
- `VC=16, depth=1`;
- `VC=1, depth=16` with `--wormhole`.

All modes use uniform-random, single-flit control traffic, 10000 Ruby cycles,
and injection rates 0.01 through 0.50.

Run or resume the 150-point sweep:

```bash
./.venv/bin/python lab/lab3/task2/run_sweep.py
```

Generate figures and the measured analysis:

```bash
./.venv/bin/python lab/lab3/task2/plot_results.py
```

Successful gem5 run directories are removed after statistics are parsed; logs
remain under ignored `artifacts/logs/`. Use `--keep-runs` to retain raw runs.
