#!/usr/bin/env bash
set -u

cd "$(dirname "$0")"

SEEDS=(101 202 303 404 505 606 707 808 909 1010)
DURATION=600

echo "========================================"
echo " SC02 Mobility Dataset"
echo " Duration : ${DURATION}s / seed"
echo " Seeds    : ${SEEDS[*]}"
echo "========================================"

for seed in "${SEEDS[@]}"; do

    echo
    echo "========================================"
    echo "[SC02] START seed=${seed}"
    echo "========================================"

    rm -rf "results/seed_${seed}"

    python3 -u run_SC02_dataset.py \
        --seed "${seed}" \
        --duration "${DURATION}"

    SUMMARY="results/seed_${seed}/summary/run_summary.json"

    if [[ ! -f "${SUMMARY}" ]]; then
        echo "[SC02] ERROR: summary missing for seed ${seed}"
        exit 1
    fi

    VALID=$(python3 - "${SUMMARY}" <<'PY'
import json
import sys

with open(sys.argv[1]) as f:
    d = json.load(f)

print("true" if d.get("valid") is True else "false")
PY
)

    echo "[SC02] seed=${seed} valid=${VALID}"

    if [[ "${VALID}" != "true" ]]; then
        echo "[SC02] STOP: seed ${seed} is INVALID."
        echo "[SC02] Fix/rerun this seed before continuing."
        exit 1
    fi

done

echo
echo "========================================"
echo " SC02 COMPLETE: ALL SEEDS VALID"
echo "========================================"
