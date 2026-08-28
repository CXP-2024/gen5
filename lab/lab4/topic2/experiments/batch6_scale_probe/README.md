# Batch 6 — Network-size capacity probe

- **Date:** 2026-08-28
- **Question:** how large a Torus3D can this gem5/Garnet setup run?

## Hard limits found (each verified by an actual failing run)

| # | Limit | Source | Consequence |
|---|---|---|---|
| 1 | `num-dirs` must be a **power of two** | Ruby directory address interleaving (`addr_range.hh:189`: match value must fit in ⌊log2(dirs)⌋ bits) | 6³=216, 10³, 12³ unusable without config-script surgery |
| 2 | `num-dirs` ≤ **256** | `AddrRange` interleave match is `uint8_t` (Python `TypeError` at 512 dirs) | 8³=512 unusable without core gem5 changes |
| 3 | ≥65 nodes needs `NUMBER_BITS_PER_SET≥nodes` **rebuild** | `Set.hh:214` compile-time bitmap (default 64) | rebuild with `scons ... NUMBER_BITS_PER_SET=256` (no logic change — bitmap capacity only) |
| 4 | default `--mem-size` too small at scale | per-dir interleaved range shrinks below granule | pass `--mem-size=8GB` |

**Practical maximum: 256 nodes (4×8×8), with 128 (4×4×8) as the
intermediate point.** Both are non-cubic, so `torus3d_transpose` is
unavailable there (needs equal dims); the other four patterns work
(xopposite needs even X — satisfied).

## Probe runs

`capacity_probe.csv` — wall time, peak RSS, latency/received sanity
values for 128/256 nodes at rates 0.05/0.30, plus a DP smoke test
(`--enable-dp` at 256 nodes) confirming the DP registry scales.
