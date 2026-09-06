#!/usr/bin/env python3
"""Adversarial audit of the DP sweep data (results_dp.csv vs gains_dp.csv
vs the older results_topic2.csv). Prints a JSON blob with all findings."""

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

DIR = Path(r"D:\THU\sophomore_spring\AI_X\gen5\lab\lab4\topic2")

def load(path):
    with (DIR / path).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

new = load("results_dp.csv")
old = load("results_topic2.csv")
gains = load("gains_dp.csv")

def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return math.nan

# index: (mode, pattern) -> {rate_text: row}
def index(rows):
    d = defaultdict(dict)
    for r in rows:
        d[(r["mode"], r["pattern"])][f"{float(r['injection_rate']):.2f}"] = r
    return d

nidx = index(new)
oidx = index(old)

def stable(r):
    return fnum(r["injection_acceptance"]) >= 0.9 and int(float(r["deadlock"])) == 0

def peak(idx, mode, pattern):
    pts = [r for r in idx[(mode, pattern)].values() if stable(r)]
    if not pts:
        return math.nan, None
    best = max(pts, key=lambda r: fnum(r["throughput"]))
    return fnum(best["throughput"]), f"{float(best['injection_rate']):.2f}"

out = {}

# ---------- basic dataset checks ----------
out["new_row_count"] = len(new)
out["new_modes"] = sorted({r["mode"] for r in new})
out["new_patterns"] = sorted({r["pattern"] for r in new})
counts = defaultdict(int)
for r in new:
    counts[(r["mode"], r["pattern"])] += 1
bad_counts = {f"{k[0]}/{k[1]}": v for k, v in counts.items() if v != 20}
out["cells_not_20_rates"] = bad_counts

# duplicated rate points?
dups = []
for (m, p), d in nidx.items():
    if len(d) != counts[(m, p)]:
        dups.append(f"{m}/{p}: {counts[(m,p)]} rows but {len(d)} distinct rates")
out["duplicate_rate_rows"] = dups

# ---------- Task 1: recompute equal-storage gains ----------
PAIRS = [("A1_cbs_v3", "A2_dpcbs_v4_s2"), ("A3_cbs_v4", "A4_dpcbs_v6_s4"),
         ("B1_esc_v2", "B2_dpesc_v3_s2"), ("B3_esc_v3", "B4_dpesc_v5_s4"),
         ("B5_esc_v4", "B6_dpesc_v7_s6")]
PATTERNS = ["torus3d_xopposite", "torus3d_tornado", "torus3d_transpose",
            "torus3d_neighbor", "uniform_random"]

recomputed = {}
for base, dp in PAIRS:
    for pat in PATTERNS:
        bp, brate = peak(nidx, base, pat)
        dpp, drate = peak(nidx, dp, pat)
        g = (dpp - bp) / bp * 100 if bp and not math.isnan(bp) else math.nan
        recomputed[(base, dp, pat)] = dict(base_peak=bp, base_rate=brate,
                                           dp_peak=dpp, dp_rate=drate, gain=g)

# compare with gains_dp.csv
gain_rows = {(g["baseline_mode"], g["dp_mode"], g["pattern"]): g for g in gains
             if g.get("kind") == "equal_storage"}
out["gains_csv_kinds"] = sorted({g["kind"] for g in gains})
out["gains_csv_equal_storage_rows"] = len(gain_rows)

mismatches = []
comparison_table = []
for key, rc in recomputed.items():
    base, dp, pat = key
    claimed = gain_rows.get(key)
    entry = dict(pair=f"{base}->{dp}", pattern=pat,
                 recomputed_gain=rc["gain"],
                 base_peak=rc["base_peak"], dp_peak=rc["dp_peak"],
                 base_rate=rc["base_rate"], dp_rate=rc["dp_rate"])
    if claimed is None:
        entry["claimed_gain"] = None
        mismatches.append(f"{base}->{dp}/{pat}: MISSING from gains_dp.csv")
    else:
        cg = fnum(claimed["gain_percent"])
        entry["claimed_gain"] = cg
        entry["claimed_base_peak"] = fnum(claimed["baseline_peak"])
        entry["claimed_dp_peak"] = fnum(claimed["dp_peak"])
        if abs(cg - rc["gain"]) > 0.1:
            mismatches.append(
                f"{base}->{dp}/{pat}: claimed {cg:.4f}% vs recomputed "
                f"{rc['gain']:.4f}% (diff {abs(cg-rc['gain']):.4f} pp)")
        if abs(entry["claimed_base_peak"] - rc["base_peak"]) > 1e-12 or \
           abs(entry["claimed_dp_peak"] - rc["dp_peak"]) > 1e-12:
            mismatches.append(
                f"{base}->{dp}/{pat}: peak values differ from gains_dp.csv "
                f"(claimed {entry['claimed_base_peak']}/{entry['claimed_dp_peak']}, "
                f"recomputed {rc['base_peak']}/{rc['dp_peak']})")
    comparison_table.append(entry)

# any extra equal_storage rows in gains_dp.csv not among expected pairs?
extra = [k for k in gain_rows if k not in recomputed]
out["gains_extra_rows"] = [f"{a}->{b}/{c}" for a, b, c in extra]
out["gain_mismatches"] = mismatches
out["gain_table"] = comparison_table

# ---------- Task 2: exact-tie forensics ----------
tie = {}
for a, b in [("B2_dpesc_v3_s2", "B3_esc_v3"), ("B4_dpesc_v5_s4", "B5_esc_v4")]:
    for pat in PATTERNS:
        da, db = nidx[(a, pat)], nidx[(b, pat)]
        rates = sorted(set(da) & set(db))
        n_tie = 0
        diff_rates = []
        for rt in rates:
            ra, rb = da[rt], db[rt]
            if ra["packets_injected"] == rb["packets_injected"] and \
               ra["packets_received"] == rb["packets_received"]:
                n_tie += 1
            else:
                diff_rates.append(rt)
        tie[f"{a} vs {b} @ {pat}"] = dict(
            rates_compared=len(rates), bit_identical=n_tie,
            first_differing_rates=diff_rates[:6])
out["ties"] = tie

# also check whether other stat columns differ at "tied" rates (deeper identity)
full_tie = {}
statcols = ["packets_injected", "packets_received", "throughput",
            "packet_latency", "network_latency", "queueing_latency",
            "average_hops", "escape_transitions", "escape_hops"]
for a, b in [("B2_dpesc_v3_s2", "B3_esc_v3"), ("B4_dpesc_v5_s4", "B5_esc_v4")]:
    for pat in PATTERNS:
        da, db = nidx[(a, pat)], nidx[(b, pat)]
        n_full = 0
        for rt in sorted(set(da) & set(db)):
            if all(da[rt][c] == db[rt][c] for c in statcols):
                n_full += 1
        full_tie[f"{a} vs {b} @ {pat}"] = n_full
out["full_stat_ties"] = full_tie

# ---------- Task 3: cross-sweep baseline reproduction ----------
old_vcs = {m: sorted({r["vcs_per_vnet"] for r in old if r["mode"] == m})
           for m in {r["mode"] for r in old}}
out["old_mode_vcs"] = old_vcs
old_patterns = sorted({r["pattern"] for r in old})
out["old_patterns"] = old_patterns

MAPPING = [("torus3d_adaptive_escape", "B5_esc_v4"),
           ("torus3d_dor_cbs", "A3_cbs_v4")]
cross = []
for old_mode, new_mode in MAPPING:
    for pat in ["uniform_random", "torus3d_neighbor", "torus3d_tornado",
                "torus3d_transpose"]:
        op, orate = peak(oidx, old_mode, pat)
        np_, nrate = peak(nidx, new_mode, pat)
        div = (np_ - op) / op * 100 if op else math.nan
        cross.append(dict(old_mode=old_mode, new_mode=new_mode, pattern=pat,
                          old_peak=op, old_rate=orate, new_peak=np_,
                          new_rate=nrate, divergence_pct=div,
                          critical=abs(div) > 2))
out["cross_sweep"] = cross

# also rate-by-rate bit identity old vs new for the mapped baselines
xrate = {}
for old_mode, new_mode in MAPPING:
    for pat in ["uniform_random", "torus3d_neighbor", "torus3d_tornado",
                "torus3d_transpose"]:
        do, dn = oidx[(old_mode, pat)], nidx[(new_mode, pat)]
        rates = sorted(set(do) & set(dn))
        ident = sum(1 for rt in rates
                    if do[rt]["packets_injected"] == dn[rt]["packets_injected"]
                    and do[rt]["packets_received"] == dn[rt]["packets_received"])
        maxrel = 0.0
        worst = None
        for rt in rates:
            a, b = fnum(do[rt]["throughput"]), fnum(dn[rt]["throughput"])
            if a:
                rel = abs(b - a) / a * 100
                if rel > maxrel:
                    maxrel, worst = rel, rt
        xrate[f"{old_mode}->{new_mode} @ {pat}"] = dict(
            rates=len(rates), bit_identical=ident,
            max_rel_thpt_diff_pct=maxrel, worst_rate=worst)
out["cross_sweep_rate_identity"] = xrate

# ---------- Task 4: ceiling audit ----------
ceiling = []
for g in gains:
    bp, dpp = fnum(g["baseline_peak"]), fnum(g["dp_peak"])
    winner = max(bp, dpp)
    if winner >= 0.49:
        ceiling.append(dict(comparison=g["comparison"], kind=g["kind"],
                            pattern=g["pattern"],
                            pair=f"{g['baseline_mode']}->{g['dp_mode']}",
                            baseline_peak=bp, dp_peak=dpp,
                            gain=fnum(g["gain_percent"])))
out["ceiling_masked"] = ceiling

# ---------- Task 5: sanity ----------
anom = []
for r in new:
    ia, dr = fnum(r["injection_acceptance"]), fnum(r["delivery_ratio"])
    if ia > 1.05:
        anom.append(f"{r['mode']}/{r['pattern']}@{r['injection_rate']}: "
                    f"injection_acceptance={ia}")
    if dr > 1.02:
        anom.append(f"{r['mode']}/{r['pattern']}@{r['injection_rate']}: "
                    f"delivery_ratio={dr}")
    for c in ["packets_injected", "packets_received", "throughput",
              "queueing_latency", "network_latency", "packet_latency",
              "average_hops", "cbs_entry_blocks", "cbs_mark_moves",
              "dp_pool_blocks", "dp_shared_grants", "escape_hops",
              "escape_transitions"]:
        v = fnum(r[c])
        if not math.isnan(v) and v < 0:
            anom.append(f"{r['mode']}/{r['pattern']}@{r['injection_rate']}: "
                        f"{c}={v} negative")
out["sanity_anomalies"] = anom

nan_rows = [f"{r['mode']}/{r['pattern']}@{r['injection_rate']}"
            for r in new if any(r[c] in ("", "nan")
            for c in ["packets_injected", "packets_received", "throughput"])]
out["nan_rows"] = nan_rows[:20]
out["nan_row_count"] = len(nan_rows)

deadlock_rows = [f"{r['mode']}/{r['pattern']}@{r['injection_rate']}"
                 for r in new if int(float(r["deadlock"])) != 0]
out["deadlock_rows"] = deadlock_rows

b1 = {}
for pat in PATTERNS:
    p, rt = peak(nidx, "B1_esc_v2", pat)
    b1[pat] = dict(peak=p, at_rate=rt,
                   in_expected_band=(0.195 <= p <= 0.197) if not math.isnan(p) else False)
out["b1_peaks"] = b1

# dp_shared_grants sanity: DP-off modes must have 0 grants; DP-on should have >0 at load
grants_viol = []
DP_ON = {"A2_dpcbs_v4_s2", "A4_dpcbs_v6_s4", "B2_dpesc_v3_s2",
         "B4_dpesc_v5_s4", "B6_dpesc_v7_s6"}
for r in new:
    g = fnum(r["dp_shared_grants"])
    if r["mode"] not in DP_ON and not math.isnan(g) and g != 0:
        grants_viol.append(f"DP-off {r['mode']}/{r['pattern']}@"
                           f"{r['injection_rate']} has dp_shared_grants={g}")
for m in DP_ON:
    for pat in PATTERNS:
        tot = sum(fnum(r["dp_shared_grants"]) for r in nidx[(m, pat)].values()
                  if not math.isnan(fnum(r["dp_shared_grants"])))
        if tot == 0:
            grants_viol.append(f"DP-on {m}/{pat}: dp_shared_grants==0 at ALL rates "
                               f"(DP may not have been active)")
out["dp_grant_violations"] = grants_viol

# vcs column matches mode table?
VCS = {"A1_cbs_v3": 3, "A2_dpcbs_v4_s2": 4, "A3_cbs_v4": 4, "A4_dpcbs_v6_s4": 6,
       "B1_esc_v2": 2, "B2_dpesc_v3_s2": 3, "B3_esc_v3": 3, "B4_dpesc_v5_s4": 5,
       "B5_esc_v4": 4, "B6_dpesc_v7_s6": 7}
vcs_viol = [f"{r['mode']} row has vcs={r['vcs_per_vnet']}" for r in new
            if int(float(r["vcs_per_vnet"])) != VCS[r["mode"]]]
out["vcs_violations"] = sorted(set(vcs_viol))

print(json.dumps(out, indent=1, default=str))
