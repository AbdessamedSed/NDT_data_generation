#!/usr/bin/env bash
set -u

cd "$HOME/omnet/NDT_journal/scenarios/SC03_traffic" || exit 1

SEEDS=(101 202 303 404 505 606 707 808 909 1010)

LOG="SC03_final_10seeds_campaign.log"

: > "$LOG"

echo "==================================================" | tee -a "$LOG"
echo "SC03 FINAL CAMPAIGN"                                | tee -a "$LOG"
echo "20 UEs / 8 active flows / LOW-MEDIUM alternating" | tee -a "$LOG"
echo "==================================================" | tee -a "$LOG"

# Keep the sudo timestamp alive during the overnight campaign.
(
    while true; do
        sudo -n true 2>/dev/null || true
        sleep 60
    done
) &
SUDO_KEEPALIVE_PID=$!

cleanup() {
    kill "$SUDO_KEEPALIVE_PID" 2>/dev/null || true
}
trap cleanup EXIT

for s in "${SEEDS[@]}"; do

    echo | tee -a "$LOG"
    echo "==================================================" | tee -a "$LOG"
    echo "START seed=$s $(date)"                            | tee -a "$LOG"
    echo "==================================================" | tee -a "$LOG"

    rm -rf "results/seed_$s"

    python3 -u run_SC03_dataset.py \
        --seed "$s" \
        --duration 600 \
        2>&1 | tee -a "$LOG"

    SUMMARY="results/seed_$s/summary/run_summary.json"

    if [ ! -f "$SUMMARY" ]; then
        echo "[CAMPAIGN] seed=$s NO SUMMARY" | tee -a "$LOG"
        continue
    fi

    python3 - "$SUMMARY" "$s" <<'PY' | tee -a "$LOG"
import json
import sys

p = sys.argv[1]
seed = sys.argv[2]

with open(p) as f:
    x = json.load(f)

c = x.get("counts", {})

print(
    f"[CAMPAIGN] seed={seed} "
    f"valid={x.get('valid')} "
    f"actions={c.get('actions')} "
    f"decisions={c.get('decisions')} "
    f"fidelity={c.get('fidelity')} "
    f"communication={c.get('communication')} "
    f"ns3_clean={x.get('ns3_log_clean')} "
    f"watchdog={x.get('runtime_watchdog_ok')}"
)
PY

    echo "END seed=$s $(date)" | tee -a "$LOG"

done

echo | tee -a "$LOG"
echo "==================================================" | tee -a "$LOG"
echo "SC03 FINAL CAMPAIGN FINISHED $(date)"              | tee -a "$LOG"
echo "==================================================" | tee -a "$LOG"
