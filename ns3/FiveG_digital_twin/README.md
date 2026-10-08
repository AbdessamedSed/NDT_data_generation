# ns-3 Digital Twin implementation

This directory contains the ns-3/5G-LENA Digital Twin implementation
used for the NDT journal dataset generation.

## Environment

- ns-3: 3.46
- 5G-LENA: v4.1.1
- Digital Twin executable: FiveG_digital_twin
- Real-time simulator: ns3::RealtimeSimulatorImpl

## DT state export

The DT state export is separated into:

- `dt_state_latest.json`: latest atomic DT state used by the online collector.
- `dt_state_history.jsonl`: complete DT state history.

The DT snapshot interval used for the current experiments is:

- 0.02 s

## Notes

Heavy ns-3 trace generation was disabled for the dataset-generation
experiments to reduce unnecessary runtime overhead.

The 5G-LENA installation also contains local RLC fixes used during the
SC02/SC03 campaigns.
