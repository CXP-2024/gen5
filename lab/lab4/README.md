# Lab 4: Deadlock-Free Adaptive Routing and Bubble Flow Control on a 3D Torus

This project implements a 4x4x4 3D Torus, congestion-aware minimal adaptive
routing (Topic 1), and Critical Bubble Scheme flow control for the unprotected
DOR mode (Topic 2, under `topic2/`). By default, the last VC in each vnet is
reserved as an escape channel. After entering the escape class, packets use non-wrap XYZ routing over
a connected 3D Mesh subnetwork and cannot return to adaptive VCs. The
`--escape-vcs` option can reserve a different number of final VCs for the
fixed-total-VC ablation.

The primary sweep compares:

- `mesh3d_xyz`: 4x4x4 Mesh with deterministic XYZ routing;
- `torus3d_dor`: 4x4x4 Torus with deterministic minimal XYZ routing;
- `torus3d_adaptive_escape`: 4x4x4 Torus with three adaptive VCs and one
  escape VC.

Run or resume the complete 600-point sweep:

```bash
./.venv/bin/python lab/lab4/run_sweep.py
```

Successful gem5 output directories are removed after parsing. Logs remain in
the ignored `artifacts/logs/` directory. Use `--keep-runs` to retain raw runs.

Generate plots and the measured summary with:

```bash
./.venv/bin/python lab/lab4/plot_results.py
```

Run the high-load 100,000-cycle progress validation without replacing the
main sweep:

```bash
./.venv/bin/python lab/lab4/run_sweep.py \
  --modes torus3d_adaptive_escape \
  --patterns uniform_random torus3d_tornado torus3d_transpose \
  --rates 1.0 --sim-cycles 100000 --jobs 3 \
  --results lab/lab4/validation.csv --force
```

The generated `summary.csv` contains the saturation summary. The PNG/PDF
figures and `analysis.md` are generated directly from `results.csv`.

## Fixed-VC ablation

The default configuration uses three adaptive VCs and one escape VC. The
following experiment holds the total at four VCs and compares `4A/0E` (unsafe),
`3A/1E`, `2A/2E`, and `1A/3E` under transpose and X-opposite traffic:

```bash
./.venv/bin/python lab/lab4/run_vc_ablation.py --force --jobs 3
./.venv/bin/python lab/lab4/plot_vc_ablation.py
```

`4A/0E` is a performance-only comparison. It intentionally has no escape
subnetwork and therefore does not carry a deadlock-freedom guarantee, even if a
finite experiment happens to complete. `vc_ablation.csv` records the guarantee
status for every point. `design.md` gives the routing invariant and proof
sketch, including why an escape packet may never return to an adaptive VC.

Run the 100,000-cycle X-opposite progress validation for the default split:

```bash
./.venv/bin/python lab/lab4/run_vc_ablation.py \
  --escape-vcs 1 --patterns torus3d_xopposite --rates 1.0 \
  --sim-cycles 100000 --jobs 1 --results lab/lab4/progress_validation.csv \
  --force
```

## Topic 2: Critical Bubble Scheme flow control

`topic2/` implements the Critical Bubble Scheme (Chen, Wang & Pinkston,
IPDPS 2011) for the unprotected `torus3d_dor` mode, gated by `--enable-cbs`.
It keeps all four VCs usable and maintains one marked free buffer slot (the
critical bubble) on every directed ring, which makes DOR constructively
deadlock-free and raises its maximum stable transpose throughput from
0.224067 to 0.257509 (about 15%), with negligible performance cost on the
other patterns (at most a 0.049-cycle full-load latency difference).

Run the 240-point CBS sweep and regenerate its figures:

```bash
./.venv/bin/python lab/lab4/topic2/run_sweep_topic2.py
./.venv/bin/python lab/lab4/topic2/plot_results_topic2.py
```

Results are `topic2/results_topic2.csv` and `topic2/summary_topic2.csv`;
design and correctness notes are in `topic2/cbs_design.md`.

## Report and presentation

The accompanying report is `report.pdf`; the 8-minute presentation is
`slides.pdf`. Rebuild them after changing data or figures with:

```bash
cd lab/lab4
../../.venv/bin/python draw_diagrams.py
pdflatex report.tex
pdflatex report.tex
pdflatex slides.tex
pdflatex slides.tex
```
