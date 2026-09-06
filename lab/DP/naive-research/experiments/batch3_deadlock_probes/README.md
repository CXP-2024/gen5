# Batch 3 — Saturation deadlock probes

- **Date:** 2026-08-28
- **Runs:** 6 probes, 200 000 cycles (20× sweep length) at injection
  rate 1.00, on the DP configurations most at risk (DP-CBS A2/A4 and
  DP-ESC B2, transpose and xopposite).

**Result: zero deadlocks, exit 0, packets delivered in the millions per
probe.** Together with batch 2 this gives 1006 deadlock-free runs,
consistent with the construction proofs in `../../dp_design.md` §4 (the
pool is never in the safety path).

**Validity: VALID.** This is the empirical leg of the safety claim.
