# NDT Timing Evidence Report

Generated: 2026-10-02T08:26:10.490966

## Experimental context

This experiment studies the temporal behavior of a 5G Network Digital Twin
pipeline.

Physical-side reference:
- OMNeT++ / INET / Simu5G
- 1 gNB
- 10 UEs
- PT observation rate: 10 Hz
- synchronization rate: 5 Hz

Digital projection:
- ns-3 / 5G-LENA

Synchronization chain:
OMNeT++/Simu5G -> CORE/EMANE -> Eclipse Ditto -> adapter -> ns-3/5G-LENA

Three synchronization-content modes are evaluated:
- M: mobility updates
- T: traffic updates
- MT: mobility and traffic updates

Important terminology:
OMNeT++/Simu5G is used as the physical-side reference / surrogate of the
physical network. It is not a measurement from a deployed physical 5G network.

## Real-time progression results

| Mode | PT sim rate (sim-s / real-s) | ns-3 sim rate (sim-s / real-s) | ns-3 wall/sim |
|---|---:|---:|---:|
| M | 1.0000 | 1.0000 | 1.0000 |
| T | 1.0000 | 0.7061 | 1.4162 |
| MT | 1.0000 | 0.6545 | 1.5280 |


## Main observations

### Physical-side reference timing

Across the evaluated configurations, OMNeT++/Simu5G progresses approximately
in lockstep with machine wall-clock time.

A value close to 1.0 sim-s / real-s means that one simulated second requires
approximately one real second.

### Digital Twin projection timing

For mobility-only synchronization:

- effective ns-3 rate: 1.0000 sim-s / real-s
- wall/sim ratio: 1.0000

For traffic-only synchronization:

- effective ns-3 rate: 0.7061 sim-s / real-s
- wall/sim ratio: 1.4162

For mobility + traffic synchronization:

- effective ns-3 rate: 0.6545 sim-s / real-s
- wall/sim ratio: 1.5280

The results show that the digital projection remains close to real time for
the mobility-only case, whereas activating traffic causes the ns-3 projection
to progress more slowly than wall-clock time.

The observed slowdown should not be interpreted simply as transmission
overhead. Traffic activation also increases the internal simulation workload
of the Digital Twin, including packet generation and 5G protocol processing.

This creates a distinction between:

1. communication-induced synchronization delay, and
2. computation-induced Digital Twin lag.

The latter can cause synchronization updates to become stale even if the
communication pipeline successfully delivers them.

## Quantitative interpretation

M mode:
- ns-3 runs at approximately 1.000x real time.

T mode:
- ns-3 runs at approximately 0.706x real time.

MT mode:
- ns-3 runs at approximately 0.654x real time.

Relative slowdown compared with real-time operation:

- T: 29.4%
- MT: 34.6%

## Survey-relevant takeaway

A simulator-based Network Digital Twin may receive synchronization updates
correctly while still losing temporal alignment with the physical-side
reference because the Digital Twin itself cannot process its workload at the
required real-time rate.

Therefore, synchronization fidelity is influenced not only by network delay,
loss, and update frequency, but also by the computational assimilation
capacity of the Digital Twin.

This motivates explicitly distinguishing communication-induced staleness from
computation-induced staleness when evaluating simulator-based Network Digital
Twins.

## Reproducibility

Raw logs and state files for M, T, and MT modes are included in this evidence
directory together with SHA-256 hashes.
