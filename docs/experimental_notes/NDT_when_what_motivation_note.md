# Preliminary Motivation: When and What to Synchronize in Network Digital Twins

## Experimental context

These observations were obtained using the current NDT prototype:

- Physical-side reference: OMNeT++ / INET / Simu5G
- Digital projection: ns-3 / 5G-LENA
- Topology: 1 gNB and 10 UEs
- PT observation rate: 10 Hz
- Synchronization rate for the What pilot: 5 Hz
- Synchronization path:
  OMNeT++/Simu5G -> CORE/EMANE -> Eclipse Ditto -> adapter -> ns-3/5G-LENA

OMNeT++/Simu5G is used as the physical-side reference (surrogate of the
physical network), not as a deployed physical 5G network.

## Observation 1: Digital Twin processing can itself create staleness

Measured effective simulation rates:

- Mobility-only synchronization (M):
  ns-3 = approximately 1.000 simulated second / real second.

- Traffic-only synchronization (T):
  ns-3 = approximately 0.653 simulated second / real second.

- Mobility + traffic synchronization (MT):
  ns-3 = approximately 0.682 simulated second / real second.

The communication pipeline delivered all synchronization updates in the
evaluated runs. However, activating the traffic workload increased the
computational load of the ns-3/5G-LENA projection and prevented it from
progressing at the same rate as wall-clock time.

This suggests that NDT staleness can have at least two distinct origins:

1. communication-induced staleness, caused by delay, loss, limited update
   frequency, or other network constraints;
2. computation-induced staleness, caused by the inability of the Digital Twin
   to assimilate and process incoming state at the required real-time rate.

Therefore, increasing synchronization frequency or synchronizing a richer
state does not necessarily improve instantaneous fidelity.

## Observation 2: The synchronized content changes domain-specific freshness

With selective synchronization and an initial M+T bootstrap:

- M synchronization:
  mean AoI_M = 0.052 s
  mean AoI_T = 6.000 s

- T synchronization:
  mean AoI_M = 4.214 s
  mean AoI_T = 1.014 s

- MT synchronization:
  mean AoI_M = 1.286 s
  mean AoI_T = 1.286 s

This validates the need to model freshness independently for different
synchronizable domains.

A synchronization action can therefore be represented as:

    a_t = (f_t, m_t)

where:

- f_t determines when/how frequently synchronization occurs;
- m_t determines what information is refreshed;
- m_t belongs to {M, T, M+T} in the current prototype.

The objective is not simply to maximize synchronization frequency, but to
select a synchronization action that balances fidelity, freshness,
communication overhead, and Digital Twin processing capacity.

## Observation 3: Inter-simulator SINR differences require care

The current experiments exhibit a substantial SINR discrepancy between
Simu5G and 5G-LENA.

This difference should not automatically be attributed to synchronization
error because the two simulators use different radio/channel abstractions and
implementations.

For the final fidelity metric, the synchronization-induced component should
be separated as much as possible from the intrinsic inter-simulator model
bias. Possible approaches include calibration, normalization, relative
variation metrics, or baseline-bias removal.

This issue should be discussed explicitly in the methodology and limitations.

## Candidate introduction motivation

Network Digital Twin synchronization is commonly viewed as a communication
problem in which higher update rates are expected to provide fresher digital
representations. Our preliminary experiments indicate that this assumption is
incomplete. Even when synchronization updates are successfully delivered,
the digital projection may fail to assimilate them at the required real-time
rate when its internal workload increases. In our 1-gNB/10-UE prototype,
the ns-3/5G-LENA projection progressed approximately in real time under
mobility-only synchronization, while traffic-enabled configurations reduced
its effective progression rate. Moreover, selectively refreshing mobility
or traffic produced markedly different domain-specific ages of information.
These observations motivate a joint When-and-What synchronization strategy
that adapts both the synchronization frequency and the refreshed state to
network dynamics, fidelity requirements, and Digital Twin processing
capacity.

## Status

These are preliminary pilot observations.

They must not yet be presented as final statistical results.
The final evaluation should use:
- multiple runs/seeds,
- longer scenarios,
- several synchronization frequencies,
- dynamic traffic regimes,
- probabilistic intra-regime traffic variation,
- communication impairment profiles,
- domain-specific AoI,
- fidelity and risk metrics.

## Selective synchronization pilot results

After introducing an initial M+T bootstrap and independent source timestamps
for mobility and traffic, the selective synchronization mechanism produced
the following preliminary results at 5 Hz:

| Mode | Mean AoI_M (s) | Mean AoI_T (s) | Position error (m) | SINR error (dB) | Throughput abs. error (B/s) | Traffic mismatch (%) | ns-3 rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| M  | 0.052 | 6.000 | 28.439 | 18.768 | 30587.4  | 70.83 | 1.000 |
| T  | 4.214 | 1.014 | 52.042 | 20.157 | 101952.5 | 21.43 | 0.653 |
| MT | 1.286 | 1.286 | 59.443 | 17.766 | 114210.4 | 40.00 | 0.682 |

AoI tail values:

- M:
  AoI_M mean/p95/max = 0.052/0.100/0.100 s
  AoI_T mean/p95/max = 6.000/10.950/11.500 s

- T:
  AoI_M mean/p95/max = 4.214/9.990/10.900 s
  AoI_T mean/p95/max = 1.014/3.850/4.500 s

- MT:
  AoI_M mean/p95/max = 1.286/4.215/4.800 s
  AoI_T mean/p95/max = 1.286/4.215/4.800 s

### Interpretation

These preliminary results confirm that mobility and traffic freshness should be
tracked independently. Refreshing only one state domain keeps that domain
fresh while the unsynchronized domain becomes progressively stale.

They also show that richer synchronization does not automatically minimize
freshness error because the Digital Twin may lose real-time processing
capability under traffic workload.

The current SINR and throughput errors must not yet be interpreted purely as
synchronization errors. They also contain intrinsic differences between
Simu5G and 5G-LENA radio and traffic behavior. The final methodology should
separate synchronization-induced error from inter-simulator model bias as
much as possible.

These values are preliminary pilot results and should be replaced by
multi-seed, longer-duration experiments before publication.
