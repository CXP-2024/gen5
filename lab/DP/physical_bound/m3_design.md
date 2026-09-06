# M3 Design Notes — ownership + cross-IU deposit (default static, no migration)

Date: 2026-09-06. Basis: plan.md M3 section + design.md v5 ("ownership is
carried by the credit itself"). Substrate: post-M2 tree (commit 73eda9a).

## Layout recap (r=2, P=4, vcs_per_vnet=8)

id 0 = E adaptive-reserve, 1 = E escape-reserve, 2 = W adaptive-reserve,
3 = W escape-reserve, 4,5 = E pool half, 6,7 = W pool half.
Home side of offset: side s reserve = [s*r,(s+1)*r); pool half s =
[2r+s*P/2, 2r+(s+1)*P/2). Side 0 = E/N/Up inports (= W/S/Down outports
upstream); side 1 = W/S/Down inports (= E/N/Up outports upstream).
Local ports stay pinned to baseline ids 0..3 (M2 invariant ⑥) — Local is
never part of a pair and is untouched by everything below.

## Decisions

1. **Ownership = credit possession.** A pool id x is allocatable by an
   upstream OutputUnit iff `is_vc_idle(x) && get_credit_count(x) > 0`.
   With vnet-0 ctrl VCs (1 buffer/VC, 1-flit packets in the whole
   experiment matrix) credit == slot == VC, exactly the design's token.

2. **Credit-init fix (makes ownership real).** Today every OutputUnit
   starts with full credits on all 8 ids; foreign ids were merely never
   iterated (M2 masks). M3 widens iteration to the full pool, so at
   construction each non-Local OutputUnit must ZERO the credits of every
   offset outside its home set (`dpphysOffsetAllowedAt(offset, side)`,
   which keeps its M2 semantics = own reserve ∪ own pool half). After
   this exactly one upstream holds each pool credit → g_E+g_W==P by
   construction. Local OutputUnits keep baseline credits (ids 0..3 used).

3. **Selector widening.** `dpphysOrderedOffsets(escape=false, side)` for
   non-Local becomes: own adaptive reserve ascending, then the FULL pool
   [2r, 2r+P) ascending. Escape stays {s*r + r-1}. Local unchanged.
   `select_free_vc_class` dpphys branch adds the `credit_count > 0`
   condition (foreign/unowned ids must never be ACTIVE'd — with 0
   credits and no migration they would deadlock the packet in static).
   `free_vc_credit_count_class` is already credit-summing — only the
   offset list widens. Static behavior: foreign pool ids always have 0
   credits at the home-opposite upstream → skipped → static ≈ M2 static.

4. **Cross-IU deposit.** In `InputUnit::wakeup` (dpphys, non-Local): the
   arriving vc's home side may differ from this inport's side (possible
   from M4 on; `forced` policy exercises it in M3). Owner IU = the
   paired inport when `dpphysHomeSideOfOffset(offset) != my side`.
   - Head flit: THIS (arrival) unit computes the outport with its own
     direction (real entry direction), then calls
     `owner->depositFlit(vc, t_flit, outport, m_id)`.
   - Body/tail: `owner->depositFlit(vc, t_flit, -1, m_id)`.
   `depositFlit` does: (head) assert idle, set_vc_active, grant_outport,
   record arrival inport; (all) insertFlit + the same stats wakeup did.
   Normal same-side path goes through the identical depositFlit call on
   `this` — one code path, PRIV/static bit-behavior preserved because
   the operations and order are exactly the old wakeup body.

5. **Asserts (P1).**
   - Arrival (relaxed from M2): reserve offsets must match the inport
     side; pool offsets may arrive on either side.
     (M2's stricter `dpphysOffsetAllowedAt` assert moves out of wakeup.)
   - Deposit (invariant ③): in depositFlit,
     `dpphysHomeSideOfOffset(offset) == side of this IU`.
   - Per-IU active count ≤ r+P/2 stays as in M2 (still valid: only home
     ids ever activate inside an IU's array).

6. **Arrival tag (§6.5's 2-bit tag).** Owner IU keeps
   `m_dpphys_arrival_inport[vc]` (int inport id, default m_id), written
   by depositFlit on head flits. Used only for credit turning + stats.

7. **grantOnRelease (SA).** Extract the SA `increment_credit` sites into
   `SwitchAllocator::grantOnRelease(InputUnit *iu, int inport, int invc,
   bool free_signal)`:
   - !isDPPhys() or Local inport → `iu->increment_credit(invc, ...)`
     verbatim (PRIV path untouched).
   - dpphys: `arrival = iu->arrivalInport(invc)`;
     non-free-signal credit OR reserve offset OR policy==static →
     credit to ARRIVAL IU (static == "return to origin side").
     policy==forced AND pool offset AND free signal → credit to
     `paired(arrival)` IU; `dpphys_grants_migrated++`; PoolOwner flip.
   Body credits always go to the arrival side; grant decisions happen
   only on the free signal (tail), so multi-flit wormhole stays safe.

8. **PoolOwner (advisory, for M4's free_f + invariant bookkeeping).**
   `Router::m_dpphys_pool_owner[3][P]` (pairs E/W, N/S, Up/Down), init =
   home side of each pool index; flipped on migration. Never consulted
   for safety in M3.

9. **Upstream state heal on migration.** When a free-signal credit
   arrives at an OutputUnit whose outVcState[vc] is IDLE (migration
   target that never sent on vc), the set-idle is a no-op; when
   ownership later returns to the original sender (which is stuck
   ACTIVE with 0 credits), the free signal repairs it to IDLE+1 credit.
   Verify OutputUnit::wakeup / OutVcState has no assert on the
   idle→idle transition; guard if it does.

10. **Network plumbing.** GarnetNetwork: whitelist policy "forced"
    (update fatal message), add helpers `dpphysIsPoolOffset(offset)`,
    `dpphysHomeSideOfOffset(offset)`, `dpphysPairOfDirn(dirn)`; add
    Scalar stat `dpphys_grants_migrated` (+regStats). Paired-inport
    lookup on Router via RoutingUnit's dirn→idx map + cbsOppositeDirn.

## Acceptance (per plan.md)

1. `regress.py --scope=priv` 15/15 bit-identical.
2. `regress.py --scope=static-smoke` 9/9 clean AND
   `dpphys_grants_migrated == 0` in every static stats.txt.
3. Forced-migration smoke: `--dpphys-policy=forced`, 1 config
   (uniform_random 0.30, 10k cycles): no panic/assert/deadlock, exit 0,
   `dpphys_grants_migrated > 0`. Added to regress.py as scope
   `forced-smoke` (discipline A: one harness).

## Out of scope for M3

STARVE/RR policies, return channel, remaining stats/flags (M4-M6).
`invariant` scope still fatals (policy=starve unimplemented) — expected
until M4.
