#!/usr/bin/env bash
set -euo pipefail

SCENARIO_DIR="$HOME/omnet/NDT_journal/scenarios/SC03_traffic"
CONFIG="$SCENARIO_DIR/config/omnetpp_SC03.ini"
BACKUP="$SCENARIO_DIR/config/omnetpp_SC03.ini.before_family_profile"
OUT="$HOME/omnet/NDT_journal/analysis/SC03_family_profile_20261007"

SEED=101
DURATION=120

mkdir -p "$OUT"

# Preserve the real SC03 configuration.
cp "$CONFIG" "$BACKUP"

restore_config() {
    cp "$BACKUP" "$CONFIG"
}
trap restore_config EXIT

echo "family,pt_final_s,ns3_final_s,source_T_final_s,dt_pt_ratio,fidelity_rows,history_rows" \
    > "$OUT/profile_summary.csv"

for FAMILY in DET EXP UNIFORM NORMAL PARETO; do

    echo
    echo "============================================================"
    echo " SC03 FAMILY PROFILE: $FAMILY"
    echo "============================================================"

    # Always restart from the untouched SC03 configuration.
    cp "$BACKUP" "$CONFIG"

    TARGET="$FAMILY" CONFIG="$CONFIG" python3 - <<'PY'
import os
import re
from pathlib import Path

target = os.environ["TARGET"]
p = Path(os.environ["CONFIG"])

family_ranges = {
    "DET": "0..1",
    "EXP": "2..3",
    "UNIFORM": "4..5",
    "NORMAL": "6..7",
    "PARETO": "8..9",
}

target_range = family_ranges[target]

lines = p.read_text().splitlines()
out = []

found = set()
i = 0

while i < len(lines):
    line = lines[i]

    m = re.match(
        r'^(\s*\*\.server\.app\[([0-9]+\.\.[0-9]+)\]\.sendInterval\s*=)(.*)$',
        line
    )

    if not m or m.group(2) not in family_ranges.values():
        out.append(line)
        i += 1
        continue

    rng = m.group(2)
    found.add(rng)

    # Capture the entire multiline sendInterval expression.
    block = [line]
    i += 1

    while block[-1].rstrip().endswith("\\") and i < len(lines):
        block.append(lines[i])
        i += 1

    if rng == target_range:
        # Accelerated profiling phases:
        # LOW 0-40 s, MEDIUM 40-80 s, HIGH 80-120 s.
        block = [
            x.replace("200s", "40s").replace("400s", "80s")
            for x in block
        ]
        out.extend(block)

    else:
        # Keep the application instantiated but make it effectively idle.
        lhs = m.group(1)
        out.append(f"{lhs} 1000s")

expected = set(family_ranges.values())

if found != expected:
    raise SystemExit(
        f"ERROR: expected sendInterval blocks {sorted(expected)}, "
        f"found {sorted(found)}"
    )

p.write_text("\n".join(out) + "\n")

print(f"[OK] Target family: {target}")
print(f"[OK] Active traffic range: [{target_range}]")
print("[OK] Other traffic families: sendInterval = 1000 s")
print("[OK] Profiling phases: 0-40 / 40-80 / 80-120 s")
PY

    echo
    echo "===== ACTIVE CONFIG ====="
    grep -nA3 'sendInterval' "$CONFIG"

    rm -rf "$SCENARIO_DIR/results/seed_${SEED}"

    echo
    echo "===== RUNNING $FAMILY ====="

    python3 -u "$SCENARIO_DIR/run_SC03_dataset.py" \
        --seed "$SEED" \
        --duration "$DURATION"

    DEST="$OUT/$FAMILY"
    rm -rf "$DEST"
    mkdir -p "$DEST"

    cp -a "$SCENARIO_DIR/results/seed_${SEED}/." "$DEST/"

    FAMILY="$FAMILY" DEST="$DEST" OUT="$OUT" python3 - <<'PY'
import csv
import json
import os
from pathlib import Path

family = os.environ["FAMILY"]
dest = Path(os.environ["DEST"])
out = Path(os.environ["OUT"])

p = dest / "fidelity/fidelity_timeseries.jsonl"

R = [
    json.loads(line)
    for line in p.open()
    if line.strip()
]

pt = max(
    float(x["pt_sim_time"])
    for x in R
    if x.get("pt_sim_time") is not None
)

dt = max(
    float(x["ns3_sim_time"])
    for x in R
    if x.get("ns3_sim_time") is not None
)

tt = [
    float(x["source_sim_time_T"])
    for x in R
    if x.get("source_sim_time_T") is not None
    and float(x["source_sim_time_T"]) >= 0
]

source_t = max(tt) if tt else None
ratio = dt / pt if pt else None

hist = dest / "raw/dt_state_history.jsonl"
history_rows = (
    sum(1 for line in hist.open() if line.strip())
    if hist.exists()
    else 0
)

row = [
    family,
    pt,
    dt,
    source_t,
    ratio,
    len(R),
    history_rows,
]

with (out / "profile_summary.csv").open("a", newline="") as f:
    csv.writer(f).writerow(row)

print()
print("RESULT", family)
print("PT final       =", pt)
print("ns3 final      =", dt)
print("source_T final =", source_t)
print("DT/PT ratio    =", ratio)
print("fidelity rows  =", len(R))
print("history rows   =", history_rows)
PY

done

restore_config
trap - EXIT

echo
echo "============================================================"
echo " FAMILY PROFILE COMPLETE"
echo "============================================================"
column -s, -t "$OUT/profile_summary.csv" || cat "$OUT/profile_summary.csv"

echo
echo "Results saved in:"
echo "$OUT"
