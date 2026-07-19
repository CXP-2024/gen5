# Lab 2 Task 1

This directory contains the reproducible sweep for five synthetic traffic
patterns on the 64-node, 8x8 Garnet mesh.

Run all 250 points (rates 0.01 through 0.50):

```bash
./.venv/bin/python lab/lab2/task1/run_sweep.py
```

The runner appends each completed point to `results.csv`, so the same command
resumes an interrupted sweep. Use `--force` to start the CSV again from zero.
Raw gem5 output and logs are kept under the ignored `artifacts/` directory.

Generate the figures and measured summary:

```bash
./.venv/bin/python lab/lab2/task1/plot_results.py
```

The primary deliverables are `latency_throughput.{pdf,png}`,
`latency_throughput_zoom.{pdf,png}`, `task1_overview.{pdf,png}`,
`results.csv`, `summary.csv`, and `analysis.md`.
