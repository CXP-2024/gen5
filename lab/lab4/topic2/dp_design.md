# Dimension Pool (DP): Buffer Pooling Across Opposing Inports

Lab 4, Topic 2 — flow control #2 (novel). Companion to the CBS work in
`report.tex`; Chinese planning notes in `dp_plan.md`.

## 1. One-line summary

At every router, the two opposing inports of one dimension (E+W, N+S, U+D)
share their pooled virtual channels under a joint occupancy cap `S`: a
direction that is temporarily hot can borrow buffer slots that its opposite,
temporarily cold, direction is not using — without moving any packet and
without touching the deadlock-freedom substrate.

## 2. Motivation and PCN analogy

In a torus, traffic is rarely balanced between the `+d` and `-d` directions
of a dimension at any given router and moment: synthetic hot patterns
(xopposite, tornado) are strictly one-sided, and even balanced patterns are
one-sided *locally* over short windows. Classical VC allocation statically
splits each inport's buffers per direction, so the cold side's VCs sit idle
while the hot side head-blocks.

This mirrors a Payment Channel Network rebalancing problem: a channel's two
directions have separate liquidity, and a one-sided flow exhausts one
direction while the other holds idle funds. DP is the NoC equivalent of a
*pooled liquidity* arrangement: both directions draw from a shared budget,
each keeping a private reserve (`r` dedicated VCs) that guarantees its own
progress — the reserve plays the role of the PCN channel reserve that keeps
the channel usable, while the pool is the rebalancing-free shared liquidity.

DP changes *where* congestion queues form (more packets held further
upstream at the hot spot instead of backing up along the path), which is
exactly the buffer-occupancy shaping that decides saturation throughput.

## 3. Mechanism

### 3.1 Scope

- Control vnets only (`buffers_per_ctrl_vc = 1`, so slot = VC = packet;
  pure counter bookkeeping, no flit-queue splitting, packets never relocate).
- Local (NI) inports and outports are never pooled; ejection and injection
  are untouched.
- Two deployments, matching the two Topic-2 substrates:
  - **DP-CBS** (routing algorithm 3, DOR + CBS): dedicated tranche =
    VC offsets `[0, r)`, pooled tranche = `[r, V)`.
  - **DP-ESC** (routing algorithm 4, adaptive + Mesh3D-routed escape VCs):
    pooled tranche = adaptive window `[0, V - esc)`, exempt tranche =
    escape window `[V - esc, V)` (escape VCs keep the last IDs, following
    the Topic-1 convention).

Tranches are **ID-pegged**, not count-based: whether a slot belongs to the
pool is a property of its VC id, fixed at configuration time. Count-based
accounting ("any `r` free VCs count as the reserve") would break the CBS
bubble invariant, because the identity of the slot the critical bubble sits
on must be stable.

### 3.2 The pool and its cap

For each router, dimension, and control vnet, define

```
pool_occ(router, dim, vnet) = occ(inport +d) + occ(inport -d)
```

where `occ` counts packets currently holding a *pooled* VC at that inport
(from allocation grant until the freeing credit returns). Admission into a
pooled VC requires

```
pool_occ < S        (S = --dp-shared-cap)
```

Equal-usable-storage accounting: a DP configuration with `d` dedicated VCs
per inport and cap `S` exposes at most `2·d + S` usable slots per dimension
pair, and is compared against the plain baseline whose *total* storage
equals that number. Any measured win therefore comes from pooling
flexibility, not extra buffers.

### 3.3 Allocation preference: shared first

When both a pooled and a dedicated VC are available, the allocator takes the
pooled one (`select_free_vc` over the pooled window first, dedicated as
fallback). Spending shared budget before private reserve maximizes bubble
mobility in the dedicated sub-ring and matches the PCN semantics of spending
pool credit before touching the reserve.

### 3.4 Accounting registry

`GarnetNetwork::m_dp_shared_occ[router][dirn6][vnet]` with
`dirn6 ∈ {E,W,N,S,U,D} = 0..5` and pair index `dirn ^ 1`:

- **Increment** at `SwitchAllocator::vc_allocate` grant time — a
  *reservation*, made before the flit moves, so admission is conservative.
- **Decrement** at `OutputUnit::wakeup` when the `is_free_signal` credit
  returns from the downstream inport.

Occupancy therefore spans grant → credit-return and includes the credit
round trip. This overestimates instantaneous buffer occupancy slightly;
since the pool is a performance mechanism (never in the safety path, §4),
the staleness can only cost throughput, never correctness.

Both bookkeeping sites address the *downstream* buffer owner symmetrically:
router R granting outport direction D calls
`dpNoteAlloc(downstream(R, D), opposite(D), vnet, offset)`, and the credit
handler at R calls `dpNoteFree` with identical addressing.

No same-cycle over-admission is possible for tori with all dimensions ≥ 3:
gem5 wakes routers sequentially, each router's SA pass is atomic, and within
one router the two outports of a dimension feed the *same* downstream pool
only when the dimension has size 2 — which `--enable-dp` rejects with a
`fatal` (§5).

## 4. Deadlock safety

DP adds an admission *restriction* on pooled slots and changes no routing.
The safety argument is therefore: the deadlock-free substrate of each
routing algorithm must keep working with the pool present.

### 4.1 Why a naive floor deadlocks (counterexample)

Suppose we only kept the cap rule "each inport retains ≥ r private slots,
pool occupancy ≤ S" with no bubble discipline inside the private slots.
Consider one ring of the torus under DOR with every node injecting toward
the same direction until all private and pooled slots on the ring hold
packets that each wait for the next hop's buffer. The cap is respected at
every router (each side under its floor and the pair under S), yet the ring
holds zero free slots — a wait-for cycle with no bubble, i.e. deadlock. The
same construction works simultaneously in both directions. A floor bounds
*how many* slots each side may hold; deadlock freedom needs an invariant
about *which* slot stays free. That invariant is exactly what CBS (or an
escape channel) provides, so DP must be composed with one of them rather
than replace them.

### 4.2 DP-CBS: depth-domain Duato

The dedicated window `[0, r)` runs CBS **verbatim** as a private sub-ring of
depth `r` (r = 2 in all experiments):

- **Ring entry** toward a marked inport requires 2 free dedicated slots
  (CBS entry rule, evaluated on the dedicated window only).
- **In-ring transit** may fill the last free dedicated slot at a marked
  inport **only if the mover itself resides in a dedicated VC**
  (`invc offset < r`). The slot it vacates is then a dedicated slot, the
  mark relocates onto it, and the sub-ring keeps its critical bubble.
  Without this residency condition, a packet sitting in a *pooled* VC could
  consume the bubble while returning its own slot to the pool — where the
  opposite direction may claim it — and the dedicated sub-ring would lose
  its bubble permanently (the failure of §4.1 in miniature).
- The pool is **never** part of the safety path: pooled admission may fail
  at any time (cap reached) and the packet simply waits for, or falls back
  to, the dedicated window, whose CBS discipline guarantees the ring drains.

This is Duato's argument transplanted to buffer depth instead of VC class:
the dedicated window is the escape *layer*, provably deadlock-free by the
CBS bubble invariant; the pooled window is the adaptive layer, allowed to
be arbitrarily congested because any packet in it is also eligible for the
escape layer at every hop.

The CBS mark-displacement rule is adapted accordingly: under DP, the mark
moves only when the mover goes dedicated→dedicated and the dedicated window
at the marked inport is thereby exhausted (`free_ded == 0` over `[0, r)`),
mirroring plain CBS's "bubble consumed" trigger on the sub-ring.

### 4.3 DP-ESC: Duato verbatim

The escape window is **exempt** from the pool: escape VCs are never counted
in `pool_occ` and never denied by the cap. Duato's theorem then applies
unchanged — every packet can always eventually take the escape channel,
which routes Mesh3D (dateline-free, acyclic CDG).

One subtlety decides where the pool check lives. Duato's premise is that a
packet *waiting on adaptive resources* still has the escape path available.
If the pool check sat only in `send_allowed`, a packet whose route
computation had already committed to a pool-full outport would stall on that
outport without re-entering the adaptive/escape choice, weakening the
premise in practice. The primary check therefore sits **inside
`outportCompute3DAdaptive`'s candidate filter**: outports whose downstream
pool is full are skipped exactly like outports with zero free adaptive
credits, so the packet either picks another minimal adaptive direction or
falls to the escape VC naturally through the existing machinery. A belt
check remains in `send_allowed` for the race where the pool fills between
route computation and switch allocation.

Consequence for statistics: for DP-ESC, pool pressure mostly appears as
routing-time candidate skips (visible indirectly as higher
`escape_transitions` / different direction mix), not as `dp_pool_blocks`,
which only counts SA-time belt-check hits.

## 5. Implementation map

| File | Change |
|---|---|
| `GarnetNetwork.py` | `enable_dp` (Bool, False), `dp_reserve` (UInt32, 2), `dp_shared_cap` (UInt32, 0) |
| `configs/network/Network.py` | `--enable-dp`, `--dp-reserve`, `--dp-shared-cap` argparse + pass-through |
| `GarnetNetwork.hh/.cc` | params, `dpGoverns/dpPooledOffset/dpSharedUsed/dpPoolFull/dpNoteAlloc/dpNoteFree/dpInit`, registry, stats, config validation |
| `SwitchAllocator.hh/.cc` | `dp_governs`, `dp_cbs_admission` (entry/transit rules of §4.2), DP branches in `send_allowed` and `vc_allocate` (shared-first selection + `dpNoteAlloc`), DP-aware CBS mark displacement |
| `OutputUnit.cc` | `dpNoteFree` on `is_free_signal` credit |
| `RoutingUnit.cc` | pool-full candidate filter in `outportCompute3DAdaptive` (§4.3) |

Configuration validation (`fatal` on violation): torus dims all ≥ 3 (a
size-2 dimension makes both outports of a router feed the same downstream
pool, allowing same-cycle cap overrun); no wormhole; routing algorithm ∈
{3, 4}; algorithm 3 requires `--enable-cbs`, `dp_reserve ≥ 2`, and
`vcs > dp_reserve`; algorithm 4 requires `escape_vcs ≥ 1`; cap ∈
`[1, 2 × pooled_per_inport]`.

New statistics: `dp_shared_grants` (allocations landing in pooled VCs),
`dp_pool_blocks` (admissions denied by the cap while a pooled VC was free).

## 6. Experiment design

4×4×4 Torus3D, 64 nodes, ctrl vnet 0, 10 000 sim-cycles, injection rates
0.05–1.00 in 0.05 steps, five patterns (xopposite, tornado, transpose,
neighbor, uniform_random). Equal usable storage per dimension pair
(`2·dedicated + S` vs baseline total):

| Family | Config | vcs | DP | Usable/pair |
|---|---|---|---|---|
| A (DOR+CBS) | A1_cbs_v3 | 3 | — | 6 |
| | A2_dpcbs_v4_s2 | 4 | r=2, S=2 | 6 |
| | A3_cbs_v4 | 4 | — | 8 |
| | A4_dpcbs_v6_s4 | 6 | r=2, S=4 | 8 |
| B (adaptive+escape) | B1_esc_v2 | 2 | — | 4 |
| | B2_dpesc_v3_s2 | 3 | S=2 | 4 |
| | B3_esc_v3 | 3 | — | 6 |
| | B4_dpesc_v5_s4 | 5 | S=4 | 6 |
| | B5_esc_v4 | 4 | — | 8 |
| | B6_dpesc_v7_s6 | 7 | S=6 | 8 |

Predictions to test:

1. **xopposite under DOR** (purely one-sided per ring): DP's headline for
   family A — the hot direction can use its dedicated 2 plus the whole cap,
   e.g. A2 gives the hot side 4 usable slots where equal-storage A1 gives 3.
2. **neighbor** (single minimal direction even for adaptive routing): the
   analogous headline for family B.
3. **tornado / transpose**: mixed pressure; measures how much pooling helps
   when both sides compete (cap contention, `dp_pool_blocks > 0` expected
   for family A).
4. **uniform_random**: symmetric load — DP should match its equal-storage
   baseline (zero-cost claim: pooling must not hurt balanced traffic).
5. **vcs=4-vs-4 and equal-vcs groups** (A2 vs A3, B2 vs B3): the honest
   residual test — same VC count, DP trades 2 slots of raw storage for
   flexibility.

Deadlock probes: 200 000 cycles at rate 1.0 for A2/A4/B2 on transpose and
xopposite (long-run safety evidence beyond the proofs of §4).

## 7. Limitations

- Requires all torus dimensions ≥ 3 (enforced; see §5).
- Occupancy includes the credit round trip, so the effective pool is
  slightly smaller than `S` under bursty reversal — conservative, never
  unsafe.
- Control vnets only; extending to data vnets (multi-flit packets) would
  need flit-level occupancy accounting.
- The direction-flip/rebalancing-latency characterization is out of scope
  for this lab (noted as future work).
