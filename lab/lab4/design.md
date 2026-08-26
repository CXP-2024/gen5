# Design and Correctness Notes

## Scope and contribution

This project adds parameterized 3D Mesh and 3D Torus topologies to Garnet, plus
three route algorithms:

| ID | Topology | Route algorithm |
|---:|---|---|
| 3 | Torus3D | Deterministic minimal XYZ DOR |
| 4 | Torus3D | Congestion-aware minimal adaptive with escape VCs |
| 5 | Mesh3D | Deterministic XYZ |

The contribution is not the claim that a 3D Torus is a new topology. It is a
Garnet implementation of congestion-aware minimal adaptive routing on that
topology, paired with a one-way, non-wrap 3D Mesh escape subnet that supplies
the progress argument.

## Topology and cost boundary

Router ID is `z * X * Y + y * X + x`. A 4x4x4 network therefore has 64
routers. Each physical neighbour pair is represented in Garnet by two directed
internal links.

For a cubic `n x n x n` network, the Mesh has
`3(n - 1)n^2` undirected neighbour pairs and the Torus has `3n^3`. At `n=4`,
that is 144 Mesh pairs versus 192 Torus pairs: the Torus uses 48 additional
pairs, or 33.3% more, to provide wrap-around links. Mesh-versus-Torus curves
thus include both routing and topology effects. The Torus DOR-versus-adaptive
comparison holds topology, link count, packet size, clock, and VC count
constant; it isolates the routing policy.

## VC partition and state invariant

Let `V` be `--vcs-per-vnet` and `E` be `--escape-vcs`. The implementation
validates `0 <= E < V` for route algorithm 4. For the safety configuration,
`E >= 1`. VCs in a vnet are partitioned as follows:

| VC range | Class | Injection and transition rule |
|---|---|---|
| `[0, V-E)` | Adaptive | New packets inject here; adaptive packets remain here while a candidate has a free adaptive VC. |
| `[V-E, V)` | Escape | A blocked adaptive head flit can move here; an escape flit can only stay here. |

The default is `V=4, E=1`, or `3A/1E`. The NI injects only into the adaptive
range. The switch allocator assigns an escape output VC only when the selected
decision is an escape decision. Once a packet owns an escape VC, all later
links are assigned only from the escape range. There is no `Escape ->
Adaptive` transition.

## Route selection

For an adaptive packet, all minimal Torus directions are candidates. In each
dimension, the minimal direction is the shorter wrap-around direction; an
equal-distance tie exposes both directions. The allocator counts usable
downstream adaptive VCs for every minimal candidate, selects the candidates
with the greatest count, and breaks ties pseudo-randomly. This remains a
minimal Torus route.

If no minimal candidate has a usable adaptive VC, the packet may transition to
the escape class. Escape routing uses the same coordinates but deliberately
does not wrap: it makes signed coordinate progress in X, then Y, then Z. The
escape path exists between every source-destination pair because the non-wrap
3D Mesh is connected, even though its path can be longer than a minimal Torus
path.

## Deadlock-freedom argument

This follows the connected acyclic escape-subset condition for adaptive
wormhole routing from J. Duato, *A Necessary and Sufficient Condition for
Deadlock-Free Adaptive Routing in Wormhole Networks*, IEEE TPDS 6(10),
1055-1067, 1995. It is a proof about legal routing and VC allocation, not an
inference from a finite simulation.

Define `C_E` as all directed links paired with Escape VCs, and construct its
channel-dependency graph: an edge `c -> d` exists when one legal Escape route
may hold channel `c` while requesting `d`.

1. `C_E` is connected. From any `(x,y,z)`, non-wrap XYZ changes signed X until
   it reaches destination X, then Y, then Z; every step is a valid Mesh3D link.
2. The `C_E` dependency graph is acyclic. Within one dimension a route has a
   fixed sign, makes strictly monotonic coordinate progress, and cannot wrap or
   reverse. Dimension changes only advance `X -> Y -> Z`. Ordering a channel
   by dimension and then coordinate progress gives a strict ranking for every
   dependency edge.
3. An Escape input is allocated only an Escape output; the implementation has
   no `Escape -> Adaptive` assignment. A blocked Escape packet therefore cannot
   have a dependency chain that leaves `C_E`.
4. A blocked Adaptive head flit with no free minimal Adaptive output VC tests
   its non-wrap Escape next hop. If it is free the flit enters `C_E`; if not,
   its outstanding wait is for that Escape resource. Thus an otherwise closed
   Adaptive wait set has an outgoing dependency into `C_E`.

For contradiction, suppose a finite protocol deadlock exists. Following an
Escape wait dependency cannot leave `C_E`; finiteness would require a cycle in
the acyclic `C_E` graph. A purely Adaptive cycle cannot persist because each
blocked Adaptive head has the Escape alternative above, and an Adaptive chain
that uses it cannot return from Escape to Adaptive. Both cases contradict the
assumption. The result assumes Garnet's normal finite buffers, reliable
credits, and fair switch arbitration.

With `E=0`, the last two steps are false. A run may finish, but it has no
deadlock-freedom guarantee and is labelled unsafe in the data and figures.

## Measurement definitions

All primary data use a 4x4x4 network, four VCs per vnet, one-flit control
traffic on vnet 0, and a 10,000-Ruby-cycle measurement window. The Ruby clock
is 2 GHz and the system clock is 1 GHz. Consequently an injection rate `r` in
packets/node/system-cycle offers `N * (sim_cycles / 2) * r` packets during the
window. Reported throughput is received packets divided by `N * sim_cycles`, in
packets/node/Ruby-cycle. Source acceptance is injected packets divided by the
offered packets. A point is called stalled when acceptance is below 0.9.

The standard patterns are uniform random, 3D neighbour, 3D tornado, and 3D
transpose. `torus3d_xopposite` sends `(x,y,z)` to `(x+X/2 mod X,y,z)` for even
X. It creates many equal-cost X-direction decisions and is useful for stressing
wrap-direction ties, but a successful finite X-opposite run is validation, not
a replacement for the dependency proof.

## Reproducibility and validation

`run_sweep.py` produces the 600-point main sweep. `run_vc_ablation.py` fixes
the total VC budget at four and compares `4A/0E`, `3A/1E`, `2A/2E`, and
`1A/3E`; its CSV records whether a configuration has a safety guarantee.

The default `3A/1E` configuration completed an additional 100,000-Ruby-cycle
X-opposite run at injection rate 1.0 with 0.998993 source acceptance, 0.999920
delivery ratio, 0.499456 throughput, and 0.000989 escape-hop fraction. A
separate vnet-2 five-flit tornado run also completed: it injected 31,948 and
received 31,885 packets in 10,000 cycles, with 478,737 adaptive hops, 110
escape hops, and 16 transitions. Existing Lab 1 Ring and Mesh route algorithms
are unaffected because the new VC classification is activated only by route
algorithm 4.
