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

## Probe runs (all exit 0, `capacity_probe.csv`)

Binary rebuilt with `NUMBER_BITS_PER_SET=256` (18 min); all runs use
`--mem-size=8GB`, 10 000 cycles, algo 4, vcs=3.

| Nodes | Dims | Wall time | Peak RSS | Sanity |
|---|---|---|---|---|
| 64 | 4×4×4 | 14 s | 1.3 GB | DP tornado on new binary, healthy |
| 128 | 4×4×8 | 29–36 s | 1.5 GB | received = expected, latency ~13 |
| 256 | 4×8×8 | 135–158 s | 2.3 GB | received = expected, latency ~15–16; **DP run works** |

Received counts match nodes × 5000 × rate at both rates → ~100%
injection acceptance, networks healthy well below saturation.

**Planning numbers for the P1 scale sweep:** RAM (15 GB) limits
parallelism to ~5 concurrent 256-node runs; a 5-mode × 3-pattern ×
10-rate sweep at both sizes is ≈ 1.5 h wall.

**Validity: VALID** (capacity facts; not performance claims).
