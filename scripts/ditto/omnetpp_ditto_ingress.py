#!/usr/bin/env python3

import json
import os
import socket
import time
import requests

UDP_RECV_IP = os.getenv("NDT_INGRESS_IP", "0.0.0.0")
UDP_RECV_PORT = int(os.getenv("NDT_INGRESS_PORT", "9999"))

DITTO_BASE_URL = os.getenv(
    "DITTO_BASE_URL",
    "http://127.0.0.1:8080/api/2/things"
)

DITTO_USER = os.getenv("DITTO_USER")
DITTO_PASSWORD = os.getenv("DITTO_PASSWORD")

NAMESPACE = os.getenv("DITTO_NAMESPACE", "my5GNetwork")
POLICY_ID = os.getenv(
    "DITTO_POLICY_ID",
    f"{NAMESPACE}:ndt-policy"
)

SNAPSHOT_THING_ID = os.getenv(
    "DITTO_SNAPSHOT_THING_ID",
    f"{NAMESPACE}:network_snapshot"
)

session = requests.Session()

if DITTO_USER and DITTO_PASSWORD:
    session.auth = (DITTO_USER, DITTO_PASSWORD)


def log(message):
    print(
        f"[{time.strftime('%H:%M:%S')}] {message}",
        flush=True
    )


def clean_id(value):
    return (
        str(value)
        .replace("[", "")
        .replace("]", "")
    )


def upsert_thing(thing_id, attributes):
    """
    Create or replace a Ditto Thing using the shared NDT policy.

    The synchronized attributes represent the complete PT state
    required by the Digital Twin.
    """

    url = f"{DITTO_BASE_URL}/{thing_id}"

    payload = {
        "policyId": POLICY_ID,
        "attributes": attributes
    }

    try:
        response = session.put(
            url,
            json=payload,
            headers={
                "Content-Type": "application/json"
            },
            timeout=2.0
        )
    except requests.RequestException as exc:
        log(
            f"Ditto request failed for {thing_id}: {exc}"
        )
        return False

    if response.status_code in (200, 201, 204):
        return True

    log(
        f"Ditto PUT failed for {thing_id}: "
        f"{response.status_code} "
        f"{response.text[:200]}"
    )

    return False


def build_node_attributes(node, sim_time, arrival_wall_time):
    attrs = {
        "x": float(node.get("x", 0.0)),
        "y": float(node.get("y", 0.0)),
        "z": float(node.get("z", 0.0)),
        "speed": float(node.get("speed", 0.0)),
        "source_sim_time": sim_time,
        "ingress_wall_time": arrival_wall_time
    }

    return attrs


def build_flow_attributes(flow, sim_time, arrival_wall_time):
    packet_size = int(
        flow.get(
            "sz",
            flow.get("packet_size", 0)
        )
    )

    interval = float(
        flow.get(
            "i",
            flow.get("interval", 0.0)
        )
    )

    src = clean_id(
        flow.get(
            "s",
            flow.get("src", "")
        )
    )

    dst = clean_id(
        flow.get(
            "d",
            flow.get("dst", "")
        )
    )

    offered_rate_bps = (
        packet_size * 8.0 / interval
        if interval > 0.0
        else 0.0
    )

    return {
        "src": src,
        "dst": dst,
        "packet_size": packet_size,
        "interval": interval,
        "offered_rate_bps": offered_rate_bps,
        "source_sim_time": sim_time,
        "ingress_wall_time": arrival_wall_time
    }



def build_snapshot_attributes(
    packet,
    sim_time,
    arrival_wall_time,
    nodes,
    flows
):
    """
    Build one atomic PT synchronization snapshot.

    Only synchronizable M+T state is stored here.
    SINR and measured throughput are intentionally excluded because
    they are independently computed by PT and DT.
    """

    compact_nodes = []

    for node in nodes:
        node_id = clean_id(
            node.get("id", "")
        )

        if not node_id:
            continue

        compact_nodes.append({
            "id": node_id,
            "x": float(node.get("x", 0.0)),
            "y": float(node.get("y", 0.0)),
            "z": float(node.get("z", 0.0)),
            "speed": float(node.get("speed", 0.0)),
        })

    compact_flows = []

    for flow in flows:
        src = clean_id(
            flow.get(
                "s",
                flow.get("src", "")
            )
        )

        dst = clean_id(
            flow.get(
                "d",
                flow.get("dst", "")
            )
        )

        if not src or not dst:
            continue

        packet_size = int(
            flow.get(
                "sz",
                flow.get("packet_size", 0)
            )
        )

        interval = float(
            flow.get(
                "i",
                flow.get("interval", 0.0)
            )
        )

        compact_flows.append({
            "s": src,
            "d": dst,
            "sz": packet_size,
            "i": interval,
        })

    return {
        "schema_version": packet.get(
            "schema_version",
            1
        ),
        "sequence": packet.get("sequence"),
        "source_sim_time": sim_time,
        "generated_wall_time": packet.get(
            "generated_wall_time"
        ),
        "ingress_wall_time": arrival_wall_time,
        "nodes": compact_nodes,
        "flows": compact_flows,
    }



# ---------------------------------------------------------------------------
# Latest synchronized state per domain.
#
# A synchronization mask indicates which domain is refreshed by the current
# packet. A missing domain must therefore retain its last synchronized value,
# not be erased from the atomic Ditto snapshot.
# ---------------------------------------------------------------------------
latest_nodes = []
latest_flows = []


def main():
    global latest_nodes, latest_flows

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM
    )

    sock.bind(
        (UDP_RECV_IP, UDP_RECV_PORT)
    )

    log(
        f"NDT ingress listening on "
        f"{UDP_RECV_IP}:{UDP_RECV_PORT}"
    )

    log(
        "Role: OMNeT -> Ditto only. "
        "No direct forwarding to ns-3."
    )

    while True:
        try:
            data, addr = sock.recvfrom(65535)

            arrival_wall_time = time.time()

            packet = json.loads(
                data.decode("utf-8")
            )

            sim_time = packet.get(
                "t",
                packet.get("sim_time")
            )

            nodes = packet.get(
                "n",
                packet.get("nodes", [])
            )

            flows = packet.get(
                "f",
                packet.get("flows", [])
            )

            mask = str(packet.get("mask", "MT")).upper()

            # Refresh only the domains selected by the synchronization action.
            # Non-selected domains retain their latest synchronized state.
            if "M" in mask:
                latest_nodes = nodes

            if "T" in mask:
                latest_flows = flows

            snapshot_attributes = build_snapshot_attributes(
                packet,
                sim_time,
                arrival_wall_time,
                latest_nodes,
                latest_flows
            )

            snapshot_ok = upsert_thing(
                SNAPSHOT_THING_ID,
                snapshot_attributes
            )

            log(
                f"sim_t={sim_time} | "
                f"snapshot={1 if snapshot_ok else 0}/1 | "
                f"nodes={len(snapshot_attributes['nodes'])} | "
                f"flows={len(snapshot_attributes['flows'])}"
            )

        except KeyboardInterrupt:
            log("Ingress stopped.")
            break

        except Exception as exc:
            log(f"Ingress error: {exc}")

    sock.close()


if __name__ == "__main__":
    main()
