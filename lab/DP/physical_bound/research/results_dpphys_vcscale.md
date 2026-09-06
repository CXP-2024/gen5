# DP-Phys VC-scale pre-study

## Setup

- 4×4×4 Torus3D, routing algorithm 4, one escape VC, control vnet 0.
- Five traffic patterns, injection rate 0.05–1.00 in steps of 0.05,
  10,000 simulated cycles, seed 1.
- Each comparison holds physical storage per direction pair constant:
  `PRIV(v)` has `2v` private slots; STARVE uses `r=1` and
  `P=2v-2`, hence `2r+P=2v`.
- The simulated data and credit links both use the requested link latency.
  The return timeout uses the analytic estimate `RTT=2L+1`: at L=8 this is
  17 cycles (`T(g>=2)=4`, `T(g=1)=34`); at L=1 it is 3 cycles
  (`T(g>=2)=1`, `T(g=1)=6`).

All six 200-point batches completed without a deadlock or assertion failure.

## Saturation-throughput delta: STARVE versus equal-storage PRIV

| L | Pair storage | STARVE layout | Neighbor | Tornado | Transpose | X-opposite | Uniform |
|---:|---:|---|---:|---:|---:|---:|---:|
| 8 | 8 | r1/P6 | −0.03% | −7.29% | −1.16% | −2.84% | −0.50% |
| 8 | 6 | r1/P4 | −0.00% | −5.94% | −1.00% | −1.73% | −0.52% |
| 8 | 4 | r1/P2 | +0.00% | −2.07% | −0.73% | −0.61% | −0.43% |
| 1 | 8 | r1/P6 | −25.5% | −35.7% | −12.3% | −17.0% | −0.0% |
| 1 | 6 | r1/P4 | −2.1% | −8.2% | −2.9% | −6.6% | −0.9% |
| 1 | 4 | r1/P2 | −0.0% | −1.6% | −0.9% | −0.7% | −0.7% |

## Immediate reading

No tested cell beats the equal-storage private baseline.  The DP-Phys counters
show that migration and return are active, so this is not a disabled-mechanism
result.  The five standard synthetic patterns are globally balanced across
opposite directions; they provide little persistent one-sided pressure for a
pair pool to exploit.  In contrast, the aggressive r1/P6 layout generates
substantial ownership/return traffic, particularly at L=1 where the return
timeouts are only 1 and 6 cycles.  The present STARVE policy therefore pays
control churn without recovering useful asymmetric capacity.

This pre-study rejects the current preregistered positive-performance
prediction on these traffic patterns.  It motivates a follow-up with an
explicitly time-varying or direction-skewed workload and a return-threshold
sensitivity sweep before making a performance claim.
