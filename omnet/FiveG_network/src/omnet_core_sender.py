#!/usr/bin/env python3

import json
import os
import socket
import time
from pathlib import Path


STATE_FILE = Path(
    os.getenv(
        "OMNET_STATE_FILE",
        "/home/abdessamedseddiki/omnet/NDT_journal/omnet/"
        "FiveG_network/simulations/network_state_latest.json",
    )
)

DEST_IP = os.getenv("NDT_DEST_IP", "10.100.0.3")
DEST_PORT = int(os.getenv("NDT_DEST_PORT", "9999"))

SOURCE_IP = os.getenv("NDT_SOURCE_IP", "10.100.0.2")

POLL_INTERVAL = float(os.getenv("NDT_POLL_INTERVAL", "0.005"))

SYNC_HZ = float(os.getenv("NDT_SYNC_HZ", "10"))
SYNC_INTERVAL = 1.0 / SYNC_HZ

SYNC_MASK = os.getenv("NDT_SYNC_MASK", "MT").upper()

if SYNC_MASK not in {"M", "T", "MT"}:
    raise ValueError(
        f"Invalid NDT_SYNC_MASK={SYNC_MASK}. "
        "Expected M, T, or MT."
    )


def load_latest_snapshot():
    if not STATE_FILE.exists():
        return None

    try:
        with STATE_FILE.open("r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(data, dict) or not data:
        return None

    return data


def build_sync_payload(snapshot, sequence):
    """
    Build the PT -> DT synchronization payload.

    Only state required to update the digital representation is transmitted.
    Physical KPIs such as SINR and measured throughput are intentionally
    excluded because they must be independently computed by both twins.
    """

    nodes = []

    if sequence == 0 or "M" in SYNC_MASK:
        for node in snapshot.get("nodes", []):
            node_type = node.get("type")

            if node_type not in ("ue", "gNB", "gnb"):
                continue

            item = {
                "id": node.get("id"),
                "type": node_type,
                "x": node.get("x"),
                "y": node.get("y"),
                "z": node.get("z", 0.0),
                "speed": node.get("speed", 0.0),
            }

            nodes.append(item)

    flows = []

    if sequence == 0 or "T" in SYNC_MASK:
        for flow in snapshot.get("flows", []):
            item = {
                "type": flow.get("type"),
                "src": flow.get("src"),
                "dst": flow.get("dst"),
                "packet_size": flow.get("packet_size"),
                "interval": flow.get("interval"),
            }

            # Offered rate is a traffic configuration parameter.
            # It is not a measured throughput KPI.
            if "offered_rate_bps" in flow:
                item["offered_rate_bps"] = flow["offered_rate_bps"]

            flows.append(item)

    return {
        "schema_version": 1,
        "sequence": sequence,
        "source": "omnet-simu5g",
        "sim_time": snapshot.get("timestamp"),
        "generated_wall_time": time.time(),
        "nodes": nodes,
        "flows": flows,
    }


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((SOURCE_IP, 0))

    print("OMNeT -> CORE/EMANE sender started")
    print(f"State file : {STATE_FILE}")
    print(f"Source     : {SOURCE_IP}")
    print(f"Destination: {DEST_IP}:{DEST_PORT}")
    print(f"Poll       : {POLL_INTERVAL * 1000:.2f} ms")
    print(f"Sync rate  : {SYNC_HZ:.3f} Hz")
    print(f"Sync period: {SYNC_INTERVAL:.6f} s")
    print(f"Sync mask  : {SYNC_MASK}")

    last_sim_time = None
    last_sent_sim_time = None
    sequence = 0

    while True:
        snapshot = load_latest_snapshot()

        if snapshot is None:
            time.sleep(POLL_INTERVAL)
            continue

        sim_time = snapshot.get("timestamp")

        # Process each newly generated PT snapshot only once.
        if sim_time == last_sim_time:
            time.sleep(POLL_INTERVAL)
            continue

        last_sim_time = sim_time

        # Synchronization policy:
        # PT observation remains fixed at 10 Hz, while transmission
        # frequency is independently controlled by NDT_SYNC_HZ.
        if (
            last_sent_sim_time is not None
            and float(sim_time) - float(last_sent_sim_time)
                < SYNC_INTERVAL - 1e-9
        ):
            time.sleep(POLL_INTERVAL)
            continue

        payload = build_sync_payload(snapshot, sequence)

        encoded = json.dumps(
            payload,
            separators=(",", ":"),
        ).encode("utf-8")

        sock.sendto(
            encoded,
            (DEST_IP, DEST_PORT),
        )

        if sequence % 100 == 0:
            print(
                f"seq={sequence} "
                f"sim_time={sim_time} "
                f"bytes={len(encoded)} "
                f"nodes={len(payload['nodes'])} "
                f"flows={len(payload['flows'])}"
            )

        sequence += 1
        last_sent_sim_time = sim_time

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
