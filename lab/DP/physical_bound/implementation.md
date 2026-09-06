# DP-Phys v4 phase-RR implementation

This is the implementation contract for the paired physical pool. The older
`design.md` remains useful as research history, but its pre-implementation
STARVE and distributed dual-service assumptions do not describe this version.

## Storage and VC numbering

The implemented default keeps exactly four physical VC slots per input port:

| Physical offset | Role |
|---|---|
| 0 | private adaptive VC |
| 1, 2 | the two pool slots physically resident in this InputUnit |
| 3 | private escape VC |

For each router and control vnet, `{E,W}`, `{N,S}`, and `{U,D}` each form one
four-slot pool. Thus an opposing pair owns eight physical slots:

```text
2 * (1 private adaptive + 1 escape) + 4 pool = 8
```

An internal link uses six *logical* VC IDs per vnet: one private, four pool,
and one escape. A pool ID is mapped at the receiving router to whichever of the
two InputUnits physically contains that slot. External/NI links remain at four
VCs. This changes ownership and addressing, not physical storage capacity.

Each physical VC records its true ingress direction and upstream VC ID. A
borrowed flit therefore computes its route from the real ingress direction and
returns its credit over the link on which it arrived, even when it is stored in
the opposing InputUnit.

The occupancy/free credit still traverses Garnet's real credit link. Pool-owner
reassignment is currently represented by a zero-latency network-level ownership
table; a newly selected peer can observe the grant without a separately modeled
grant wire delay. Performance results should therefore be described as an upper
bound until explicit grant transport is modeled.

## Credit and arbitration rules

- Private adaptive and escape credits never migrate.
- A pool slot always has one owner; there is no receiver-held idle-credit
  state.
- Allocation order is private adaptive, owned pool, borrowable peer pool, then
  escape through the existing adaptive-routing fallback.
- `owner_cap=3` with a four-slot pool lets one side own at most three credits,
  so its peer always retains at least one.
- `pressure` gives a released credit to the peer only when the peer's reserved
  region is more occupied. Equal pressure keeps it with the last holder, which
  provides the requested burst/large-packet stickiness.
- If a direction needs a pool slot and has none idle, `pressure` may immediately
  claim an idle peer-owned slot up to the owner cap. This is the voluntary-return
  path and prevents an idle sender from hoarding usable credits.
- `rts` and `rr` are retained as policy controls for experiments.

Every paired pool has one modeled read service and one modeled write service
per cycle (per control vnet). Read access uses a complementary two-phase RR:

| Phase | Side 0 (E/N/U) | Side 1 (W/S/D) |
|---|---|---|
| A (even cycle) | RES | POOL |
| B (odd cycle) | POOL | RES |

Each bank has its own RR pointer. RES rotates over the private adaptive and
escape slots. POOL rotates over all four physical pool slots, including slots
hosted by the opposite InputUnit. The selected pool flit uses the crossbar lane
of its true ingress direction, so one RES read and the opposing POOL read can
proceed together even if their backing slots reside in the same InputUnit.
Exactly one direction can query POOL in a cycle, making pool read conflicts
zero by construction. Pool write admission remains limited to one allocation
per pair and cycle.

The current model requires one-flit control VC buffers and Torus3D adaptive
routing (`--routing-algorithm=4`). Escape VCs remain private, so the existing
deadlock-avoidance substrate does not depend on pool ownership.

## Command-line interface

The default 1+4+1 logical layout is enabled with:

```text
--routing-algorithm=4
--vcs-per-vnet=4
--escape-vcs=1
--enable-dpphys
--dpphys-private-vcs=1
--dpphys-pool-vcs=4
--dpphys-owner-cap=3
--dpphys-policy=pressure
```

`--enable-dpphys` is mutually exclusive with the older `--enable-dp`, CBS, and
wormhole modes. Configuration validation checks both that physical VC count is
`private + pool/2 + escape` and that `private + escape = pool/2`, which keeps
the two RR banks equally sized.

The implementation exports these statistics:

- `dpphys_pool_allocations`
- `dpphys_owned_pool_allocations`
- `dpphys_demand_reclaims`
- `dpphys_owner_migrations`
- `dpphys_release_handoffs`
- `dpphys_release_keeps`
- `dpphys_ownership_wait_starts`
- `dpphys_ownership_wait_completions`
- `dpphys_ownership_wait_cycles`
- `dpphys_ownership_wait_max`
- `dpphys_pool_write_blocks`
- `dpphys_pool_read_conflicts`
- `dpphys_pool_reads`
- `dpphys_reserved_reads`
- `dpphys_borrowed_peak`

Pool allocations, Pool reads, reserved reads, and migration destinations are
also exported by true ingress direction (E/W/N/S/U/D). This separates a policy
that merely migrates frequently from one that sends credits toward the loaded
side.

An ownership-wait episode starts when an adaptive VC allocation requests more
Pool ownership while the direction owns fewer credits than its cap. It
completes when a credit next migrates to that direction. An immediate demand
reclaim is therefore a completed zero-cycle episode. The total and maximum
wait are measured in Garnet network cycles; an absent episode means that the
direction never requested additional ownership.

The synthetic tester includes `torus3d_x_reversal`. It sends one-hop +X traffic
for `--traffic-epoch-cycles=N` source cycles, then one-hop -X traffic for N
cycles, and repeats. Thus the hot true input alternates West/East. Owner changes
can be traced with `--debug-flags=DPPhys`; the trace records router, pair, slot,
old/new owner, and whether the change came from demand reclaim or release.

Use `run_sweep_dpphys.py` for equal-physical comparisons against the private
four-VC baseline. It supports repeated random seeds and pressure owner-cap
ablations at 2, 3, and 4 credits. The full experiment rationale is in
`evaluation_plan.md`. The current structure figure is
`figures/dpphys_single_node_v3_rr.png`.
