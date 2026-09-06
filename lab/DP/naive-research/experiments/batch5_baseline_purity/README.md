# Batch 5 — Baseline purity check (audit)

- **Date:** 2026-08-28 (part of the adversarial audit)
- **Method:** the post-DP binary re-ran all baseline (non-DP) rate
  points that also existed in the pre-DP sweeps and compared every stat
  column bit-for-bit against the archived batch 1/2 results.

**Result: 160/160 shared rate points bit-identical.** The DP code
changes do not perturb any baseline code path, so no measured gain can
come from accidental changes to the baselines.

A second bit-identity result from the same audit: B2 (DP-ESC vcs=3 S=2)
≡ B3 (plain vcs=3) at **all 20 rates, all stat columns** on tornado and
neighbor — with S = pooled-VCs-per-inport and one-sided traffic the cap
is provably redundant, which is why the correct C=4 claim is budget
efficiency rather than a throughput gain.

**Raw rerun directories were not retained** (they were transient audit
artifacts); the comparison verdicts are recorded here and in
`../../dp_report.md` §4. Reproduce by re-running `run_sweep_topic2.py` /
`run_sweep_dp.py` baseline modes and diffing against batch 1/2 CSVs.

**Validity: VALID** (methodological evidence).
