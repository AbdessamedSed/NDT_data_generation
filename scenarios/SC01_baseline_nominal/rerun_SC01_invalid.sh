#!/usr/bin/env bash
set -u

cd "$HOME/omnet/NDT_journal/scenarios/SC01_baseline_nominal"

for SEED in 101 909 1010; do

    echo
    echo "============================================================"
    echo " SC01 RE-RUN - SEED $SEED"
    echo "============================================================"
    date

    python3 -u run_SC01_dataset.py \
        --seed "$SEED" \
        --duration 600

    OUT="$HOME/omnet/NDT_journal/scenarios/SC01_baseline_nominal/results/seed_$SEED"

    echo
    echo "--- SUMMARY ---"
    cat "$OUT/summary/run_summary.json"

    echo
    echo "--- COUNTS ---"
    wc -l \
        "$OUT/raw/actions.jsonl" \
        "$OUT/raw/communication_metrics.jsonl" \
        "$OUT/observations/decision_observations.jsonl" \
        "$OUT/fidelity/fidelity_timeseries.jsonl"

    sleep 10
done
