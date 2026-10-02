#!/usr/bin/env bash
set -euo pipefail

DURATION=12
HZ=5
ROOT="$HOME/ndt_what_final"

mkdir -p "$ROOT"

for MASK in M T MT; do

    echo
    echo "======================================================"
    echo " FINAL WHAT PILOT: ${MASK} @ ${HZ} Hz"
    echo "======================================================"

    SIM_DURATION=$DURATION \
    SYNC_HZ=$HZ \
    SYNC_MASK=$MASK \
    "$HOME/run_ndt_bus_1h.sh"

    EXP=$(cat "$HOME/ndt_experiments/LATEST")

    echo "Waiting for ns-3 completion..."

    for _ in $(seq 1 100); do
        if ! pgrep -f 'build/FiveG_digital_twin' >/dev/null 2>&1; then
            break
        fi
        sleep 0.5
    done

    sleep 1

    DEST="$ROOT/${MASK}"

    rm -rf "$DEST"
    mkdir -p "$DEST"

    cp \
      "$HOME/omnet/NDT_journal/omnet/FiveG_network/simulations/pt_state.jsonl" \
      "$DEST/"

    cp \
      "$HOME/ns-3-dev/dt_state.json" \
      "$DEST/"

    cp -r "$EXP"/* "$DEST/"

    echo -n "PT snapshots : "
    wc -l < "$DEST/pt_state.jsonl"

    echo -n "Adapter sends: "
    grep -c 'Sent to ns-3:' "$DEST/ditto_ns3_adapter.log"

done

echo
echo "Final What pilot completed."
