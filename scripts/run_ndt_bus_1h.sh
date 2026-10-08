#!/usr/bin/env bash

set -euo pipefail

HOME_DIR="/home/abdessamedseddiki"

# Simulation duration in seconds.
# Example:
# SIM_DURATION=30 ./run_ndt_bus_1h.sh
SIM_DURATION="${SIM_DURATION:-1200}"

# ns-3 starts before the PT to establish the control path.
# Keep it alive long enough to cover the complete PT experiment.
NS3_GUARD="${NS3_GUARD:-5}"
NS3_DURATION="$((SIM_DURATION + NS3_GUARD))"

# PT synchronization source frequency.
SYNC_HZ="${SYNC_HZ:-10}"
SYNC_MASK="${SYNC_MASK:-MT}"

# Convert Hz to seconds with sufficient precision.
SYNC_INTERVAL="$(python3 -c "print(f'{1.0/float(\"$SYNC_HZ\"):.9f}')")"

OMNET_ROOT="$HOME_DIR/omnet/NDT_journal/omnet/FiveG_network"
OMNET_SIM="$OMNET_ROOT/simulations"

DITTO_ROOT="$HOME_DIR/ditto/FiveG_network"
DITTO_DOCKER="$HOME_DIR/ditto/deployment/docker"

NS3_ROOT="$HOME_DIR/ns-3-dev"

CORE_SCENARIO="$HOME_DIR/core/ndt_emane_test.py"
CORE_PROFILE="$HOME_DIR/core/ndt_emane_profile_1h.py"

TMUX_SESSION="ndt_bus_1h"

STAMP="$(date +%Y%m%d_%H%M%S)"
EXP_DIR="$HOME_DIR/ndt_experiments/bus_1h_${STAMP}"

mkdir -p "$EXP_DIR"

echo "$EXP_DIR" > "$HOME_DIR/ndt_experiments/LATEST"

echo "Experiment directory:"
echo "$EXP_DIR"
echo

# ---------------------------------------------------------------------------
# PRE-FLIGHT
# ---------------------------------------------------------------------------

sudo -v

sudo systemctl start core-daemon

# Stop processes left from interactive validation.
sudo pkill -f ditto_ns3_adapter.py 2>/dev/null || true
sudo pkill -f omnet_core_sender.py 2>/dev/null || true
sudo pkill -f omnetpp_ditto_ingress.py 2>/dev/null || true
sudo pkill -f FiveG_digital_twin 2>/dev/null || true
sudo pkill -f ndt_emane_test.py 2>/dev/null || true
sudo pkill -f ndt_emane_1h.py 2>/dev/null || true

sleep 2

# This experiment requires the CORE control network exclusively.
# Delete stale test CORE sessions from the previous validation work.
while read -r sid; do
    if [[ "$sid" =~ ^[0-9]+$ ]]; then
        core-cli session -i "$sid" delete || true
    fi
done < <(
    core-cli query sessions 2>/dev/null |
    awk 'NR>1 {gsub(/ /,"",$1); print $1}'
)

rm -f /tmp/ndt_core_session_id

# Remove stale live PT state.
rm -f \
    "$OMNET_SIM/network_state_latest.json" \
    "$OMNET_SIM/network_state_latest.json.tmp"

# ---------------------------------------------------------------------------
# DITTO HEALTH
# ---------------------------------------------------------------------------

if ! curl -fsS \
    -u ditto:ditto \
    'http://127.0.0.1:8080/api/2/search/things?option=size(1)' \
    >/dev/null
then
    echo "Ditto is not reachable. Starting Docker deployment..."

    (
        cd "$DITTO_DOCKER"
        docker-compose up -d
    )

    echo "Waiting for Ditto..."

    for _ in $(seq 1 60); do
        if curl -fsS \
            -u ditto:ditto \
            'http://127.0.0.1:8080/api/2/search/things?option=size(1)' \
            >/dev/null
        then
            break
        fi

        sleep 2
    done
fi

curl -fsS \
    -u ditto:ditto \
    'http://127.0.0.1:8080/api/2/search/things?option=size(1)' \
    >/dev/null

# ---------------------------------------------------------------------------
# EXPERIMENT METADATA
# ---------------------------------------------------------------------------

cat > "$EXP_DIR/experiment.txt" <<EOF
experiment=bus_1h
created=$(date --iso-8601=seconds)
omnet_config=JournalBus1h
duration_sim_s=$SIM_DURATION
num_ues=10
num_gnbs=1
sync_source_sampling_s=0.1
core_model=EMANE_RF_PIPE
ns3_num_ues=10
ns3_num_gnbs=1
EOF

# ---------------------------------------------------------------------------
# TMUX
# ---------------------------------------------------------------------------

tmux kill-session \
    -t "$TMUX_SESSION" \
    2>/dev/null || true

tmux new-session \
    -d \
    -s "$TMUX_SESSION" \
    -n status

# ---------------------------------------------------------------------------
# CORE
# ---------------------------------------------------------------------------

# CORE must be started from the current authenticated terminal.
# Starting sudo inside a new tmux PTY may require another password.
sudo -n nohup env PYTHONUNBUFFERED=1 \
    core-python "$CORE_SCENARIO" \
    > "$EXP_DIR/core.log" 2>&1 \
    < /dev/null &

CORE_PID=$!
echo "$CORE_PID" > "$EXP_DIR/core.pid"

echo "Waiting for CORE session..."

CORE_SESSION_ID=""

for _ in $(seq 1 60); do
    CORE_SESSION_ID="$(
        core-cli query sessions 2>/dev/null |
        awk 'NR>1 && $1 ~ /^[0-9]+$/ {print $1; exit}'
    )"

    if [[ -n "$CORE_SESSION_ID" ]]; then
        break
    fi

    sleep 1
done

if [[ -z "$CORE_SESSION_ID" ]]; then
    echo "ERROR: CORE session did not start."
    echo
    echo "CORE LOG:"
    cat "$EXP_DIR/core.log" 2>/dev/null || true
    exit 1
fi

echo "$CORE_SESSION_ID" > /tmp/ndt_core_session_id

echo "CORE session: $CORE_SESSION_ID"

# ---------------------------------------------------------------------------
# DITTO INGRESS inside ditto-gateway
# ---------------------------------------------------------------------------

core-python - <<PY
from core.api.grpc import client

core = client.CoreGrpcClient()
core.connect()

core.node_command(
    ${CORE_SESSION_ID},
    3,
    """
cd ${DITTO_ROOT} &&
export NDT_INGRESS_IP='0.0.0.0' &&
export NDT_INGRESS_PORT='9999' &&
export DITTO_BASE_URL='http://172.16.0.254:8080/api/2/things' &&
export DITTO_USER='ditto' &&
export DITTO_PASSWORD='ditto' &&
export DITTO_NAMESPACE='my5GNetwork' &&
export DITTO_POLICY_ID='my5GNetwork:ndt-policy' &&
python3 -u omnetpp_ditto_ingress.py \
> '${EXP_DIR}/ditto_ingress.log' 2>&1
""",
    wait=False,
    shell=True,
)
PY

# ---------------------------------------------------------------------------
# NS-3
# ---------------------------------------------------------------------------

tmux new-window \
    -t "$TMUX_SESSION" \
    -n ns3 \
    "cd '$NS3_ROOT' && \
     ./build/FiveG_digital_twin \
       --numUes=10 \
       --numGnbs=1 \
       --simTime=$NS3_DURATION \
     2>&1 | tee '$EXP_DIR/ns3.log'"

echo "Waiting for ns-3 readiness..."

NS3_READY=0

for _ in $(seq 1 60); do
    if grep -q 'NS3_READY_FOR_DATA' "$EXP_DIR/ns3.log" 2>/dev/null; then
        NS3_READY=1
        break
    fi

    sleep 0.5
done

if [[ "$NS3_READY" -ne 1 ]]; then
    echo "ERROR: ns-3 did not become ready."
    tail -30 "$EXP_DIR/ns3.log" 2>/dev/null || true
    exit 1
fi

echo "ns-3 ready."

# ---------------------------------------------------------------------------
# DITTO -> NS-3 adapter
# ---------------------------------------------------------------------------

sudo -n nohup env \
    DITTO_USER='ditto' \
    DITTO_PASSWORD='ditto' \
    DITTO_NAMESPACE='my5GNetwork' \
    DITTO_POLL_INTERVAL='0.02' \
    NS3_TAP_INTERFACE='thetap' \
    NS3_TARGET_IP='10.1.1.2' \
    NS3_TARGET_MAC='00:00:00:00:00:02' \
    NS3_TARGET_PORT='5000' \
    NS3_SOURCE_IP='10.1.1.10' \
    NS3_SOURCE_MAC='06:53:88:13:15:81' \
    NS3_UDP_CHUNK_SIZE='1100' \
    python3 -u "$DITTO_ROOT/ditto_ns3_adapter.py" \
    > "$EXP_DIR/ditto_ns3_adapter.log" 2>&1 \
    < /dev/null &

echo $! > "$EXP_DIR/adapter.pid"

sleep 1

# ---------------------------------------------------------------------------
# PREPARE PT SOURCE
# ---------------------------------------------------------------------------

# Remove the live snapshot left by a previous experiment.
# The sender must wait for a snapshot produced by the new OMNeT run.
rm -f "$OMNET_SIM/network_state_latest.json"

# ---------------------------------------------------------------------------
# OMNeT -> CORE/EMANE sender
# Start it BEFORE OMNeT so no initial PT snapshot is missed.
# ---------------------------------------------------------------------------

core-python - <<PY_CORE
from core.api.grpc import client

core = client.CoreGrpcClient()
core.connect()

core.node_command(
    ${CORE_SESSION_ID},
    2,
    """
cd ${OMNET_ROOT}/src &&
export NDT_SYNC_HZ='${SYNC_HZ}' &&
export NDT_SYNC_MASK='${SYNC_MASK}' &&
python3 -u omnet_core_sender.py \
> '${EXP_DIR}/omnet_sender.log' 2>&1
""",
    wait=False,
    shell=True,
)
PY_CORE

echo "Waiting for PT sender startup..."
sleep 1

# Verify that the sender process is alive inside the CORE node.
core-python - <<PY_SENDER_CHECK
from core.api.grpc import client

core = client.CoreGrpcClient()
core.connect()

result = core.node_command(
    ${CORE_SESSION_ID},
    2,
    "pgrep -af omnet_core_sender.py || true",
    wait=True,
    shell=True,
)

print(result)
PY_SENDER_CHECK

# ---------------------------------------------------------------------------
# OMNeT++
# Start PT only after the complete downstream chain is ready.
# ---------------------------------------------------------------------------

tmux new-window \
    -t "$TMUX_SESSION" \
    -n omnet \
    "source '$HOME_DIR/omnet/omnetpp-6.3.0/setenv' && \
     cd '$OMNET_SIM' && \
     ../FiveG_network \
       -u Cmdenv \
       -c JournalBus1h \
       -f journal_bus_1h.ini \
       --sim-time-limit=${SIM_DURATION}s \
       --**.dtConnector.samplingInterval=0.1s \
     2>&1 | tee '$EXP_DIR/omnet.log'"

echo "Waiting for first PT snapshot..."

OMNET_READY=0

for _ in $(seq 1 120); do
    if [[ -s "$OMNET_SIM/network_state_latest.json" ]]; then
        if python3 - "$OMNET_SIM/network_state_latest.json" <<'PY_STATE' >/dev/null 2>&1
import json
import sys

x = json.load(open(sys.argv[1]))
t = float(x.get("timestamp", 0.0))

raise SystemExit(0 if t > 0.0 else 1)
PY_STATE
        then
            OMNET_READY=1
            break
        fi
    fi

    sleep 0.1
done

if [[ "$OMNET_READY" -ne 1 ]]; then
    echo "ERROR: OMNeT live state was not generated."
    exit 1
fi

echo "First PT snapshot generated."

# ---------------------------------------------------------------------------
# DYNAMIC EMANE PROFILE
# ---------------------------------------------------------------------------

tmux new-window \
    -t "$TMUX_SESSION" \
    -n emane-profile \
    "export NDT_EXP_DIR='$EXP_DIR'; \
     core-python '$CORE_PROFILE' \
     2>&1 | tee '$EXP_DIR/emane_profile.log'"

# ---------------------------------------------------------------------------
# STATUS MONITOR
# ---------------------------------------------------------------------------

tmux send-keys \
    -t "$TMUX_SESSION:status" \
    "while true; do
        clear
        echo '===== NDT 1H EXPERIMENT ====='
        echo 'Experiment: $EXP_DIR'
        echo
        date
        echo
        echo '--- CORE ---'
        core-cli query sessions || true
        echo
        echo '--- PROCESSES ---'
        ps -eo pid,etime,%cpu,%mem,cmd |
          grep -E 'FiveG_digital_twin|ditto_ns3_adapter|FiveG_network|omnet_core_sender|omnetpp_ditto_ingress|ndt_emane' |
          grep -v grep || true
        echo
        echo '--- LIVE PT STATE ---'
        ls -lh '$OMNET_SIM/network_state_latest.json' 2>/dev/null || true
        echo
        echo '--- LAST EMANE PROFILE ---'
        tail -1 '$EXP_DIR/emane_profile.log' 2>/dev/null || true
        echo
        echo '--- ADAPTER ---'
        tail -3 '$EXP_DIR/ditto_ns3_adapter.log' 2>/dev/null || true
        echo
        echo '--- NS3 ---'
        grep -E 'NS3-REASSEMBLY|NS3-MOBILITY|NS_ASSERT|NS_FATAL' '$EXP_DIR/ns3.log' |
          tail -5 || true
        sleep 30
     done" \
    C-m

# ---------------------------------------------------------------------------
# COMPLETION WATCHER
# ---------------------------------------------------------------------------

tmux new-window \
    -t "$TMUX_SESSION" \
    -n completion \
    "while pgrep -f '${OMNET_ROOT}/FiveG_network' >/dev/null; do
        sleep 30
     done

     echo 'OMNeT run finished at:' \$(date --iso-8601=seconds) |
       tee '$EXP_DIR/FINISHED.txt'

     sleep 5"

echo
echo "=============================================================="
echo " NDT experiment launched successfully"
echo "=============================================================="
echo "tmux session : $TMUX_SESSION"
echo "experiment   : $EXP_DIR"
echo "CORE session : $CORE_SESSION_ID"
echo
echo "You can now disconnect SSH."
echo
echo "To watch it:"
echo "  tmux attach -t $TMUX_SESSION"
echo
echo "To detach from tmux:"
echo "  Ctrl+B then D"
echo
echo "After coming back:"
echo "  cat $HOME_DIR/ndt_experiments/LATEST"
echo
