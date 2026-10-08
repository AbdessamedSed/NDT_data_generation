#!/usr/bin/env bash
set -u

cd "$HOME/omnet/NDT_journal/scenarios/SC01_baseline_nominal"

SEEDS=(
    101
    202
    303
    404
    505
    606
    707
    808
    909
    1010
)

for SEED in "${SEEDS[@]}"; do

    echo
    echo "============================================================"
    echo " SC01 DATASET - SEED $SEED"
    echo "============================================================"
    date

    python3 -u run_SC01_dataset.py \
        --seed "$SEED" \
        --duration 600

    STATUS=$?

    if [[ $STATUS -ne 0 ]]; then
        echo "ERROR: seed $SEED failed with status $STATUS"
        exit $STATUS
    fi

    OUT="$HOME/omnet/NDT_journal/scenarios/SC01_baseline_nominal/results/seed_$SEED"

    echo
    echo "--- Result counts ---"

    wc -l \
        "$OUT/raw/actions.jsonl" \
        "$OUT/raw/sync_messages.jsonl" \
        "$OUT/raw/communication_metrics.jsonl" \
        "$OUT/observations/decision_observations.jsonl" \
        "$OUT/fidelity/fidelity_timeseries.jsonl"

    echo
    echo "--- Summary ---"

    cat "$OUT/summary/run_summary.json"

    echo
    echo "Seed $SEED completed."
    echo "Waiting 10 s before next seed..."

    sleep 10

done

echo
echo "============================================================"
echo " SC01 - ALL 10 SEEDS COMPLETED"
echo "============================================================"
date
