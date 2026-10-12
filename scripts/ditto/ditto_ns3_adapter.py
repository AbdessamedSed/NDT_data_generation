#!/usr/bin/env python3

import hashlib
import json
import os
import time
import requests

from scapy.all import Ether, IP, UDP, Raw, sendp


DITTO_SEARCH_URL = os.getenv(
    "DITTO_SEARCH_URL",
    "http://127.0.0.1:8080/api/2/search/things"
)

DITTO_USER = os.getenv("DITTO_USER")
DITTO_PASSWORD = os.getenv("DITTO_PASSWORD")

NAMESPACE = os.getenv(
    "DITTO_NAMESPACE",
    "my5GNetwork"
)


DITTO_SNAPSHOT_URL = os.getenv(
    "DITTO_SNAPSHOT_URL",
    f"http://127.0.0.1:8080/api/2/things/"
    f"{NAMESPACE}:network_snapshot"
)

INTERFACE = os.getenv(
    "NS3_TAP_INTERFACE",
    "thetap"
)

TARGET_IP = os.getenv(
    "NS3_TARGET_IP",
    "10.1.1.2"
)

TARGET_MAC = os.getenv(
    "NS3_TARGET_MAC",
    "00:00:00:00:00:02"
)

TARGET_PORT = int(
    os.getenv(
        "NS3_TARGET_PORT",
        "5000"
    )
)

# Maximum application payload carried in one UDP frame.
# The complete Ethernet/IP/UDP frame remains safely below
# a conventional 1500-byte MTU.
UDP_CHUNK_SIZE = int(
    os.getenv(
        "NS3_UDP_CHUNK_SIZE",
        "1100"
    )
)

SOURCE_IP = os.getenv(
    "NS3_SOURCE_IP",
    "10.1.1.10"
)

SOURCE_MAC = os.getenv(
    "NS3_SOURCE_MAC",
    "06:53:88:13:15:81"
)

POLL_INTERVAL = float(
    os.getenv(
        "DITTO_POLL_INTERVAL",
        "0.5"
    )
)

session = requests.Session()

if DITTO_USER and DITTO_PASSWORD:
    session.auth = (
        DITTO_USER,
        DITTO_PASSWORD
    )


def log(message):
    print(
        f"[{time.strftime('%H:%M:%S')}] "
        f"{message}",
        flush=True
    )


def clean_id(value):
    value = str(value)

    if ":" in value:
        value = value.split(":", 1)[1]

    return (
        value
        .replace("[", "")
        .replace("]", "")
    )


def fetch_things():
    """
    Retrieve every Thing from the configured Ditto namespace.

    Eclipse Ditto limits HTTP search pages to 200 results.
    Cursor-based paging is therefore required when the namespace
    contains more than 200 Things.
    """

    all_items = []
    cursor = None
    page_number = 0

    while True:
        page_number += 1

        options = [
            "size(200)",
            "sort(+thingId)"
        ]

        if cursor:
            options.append(
                f"cursor({cursor})"
            )

        params = {
            "namespaces": NAMESPACE,
            "fields": "thingId,attributes",
            "option": ",".join(options)
        }

        response = session.get(
            DITTO_SEARCH_URL,
            params=params,
            timeout=10.0
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"Ditto GET failed on page {page_number}: "
                f"{response.status_code} "
                f"{response.text[:300]}"
            )

        body = response.json()

        items = body.get(
            "items",
            []
        )

        all_items.extend(items)

        # Per-poll page logging disabled for high-frequency experiments.

        cursor = body.get("cursor")

        if not cursor:
            break

    return all_items


def fetch_atomic_snapshot():
    """
    Fetch the single atomic synchronization snapshot from Ditto.
    """

    response = session.get(
        DITTO_SNAPSHOT_URL,
        timeout=2.0
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Ditto snapshot GET failed: "
            f"{response.status_code} "
            f"{response.text[:300]}"
        )

    thing = response.json()

    attrs = thing.get(
        "attributes",
        {}
    )

    sim_time = attrs.get(
        "source_sim_time"
    )

    return {
        "t": sim_time,
        "n": attrs.get("nodes", []),
        "f": attrs.get("flows", []),
    }


def classify_things(items):
    nodes = []
    flows = []

    for item in items:
        thing_id = item.get(
            "thingId",
            ""
        )

        attrs = item.get(
            "attributes",
            {}
        )

        local_id = clean_id(
            thing_id
        )

        # Flow thing
        if (
            "src" in attrs
            and "dst" in attrs
        ):
            flows.append({
                "s": clean_id(
                    attrs["src"]
                ),
                "d": clean_id(
                    attrs["dst"]
                ),
                "sz": int(
                    attrs.get(
                        "packet_size",
                        0
                    )
                ),
                "i": float(
                    attrs.get(
                        "interval",
                        0.0
                    )
                )
            })

            continue

        # UE/gNB thing
        if (
            local_id.startswith("ue")
            or local_id.startswith("gnb")
        ):
            nodes.append({
                "id": local_id,
                "x": float(
                    attrs.get("x", 0.0)
                ),
                "y": float(
                    attrs.get("y", 0.0)
                ),
                "z": float(
                    attrs.get("z", 0.0)
                ),
                "speed": float(
                    attrs.get(
                        "speed",
                        0.0
                    )
                )
            })

    return nodes, flows


def build_payload(items):
    nodes, flows = classify_things(
        items
    )

    source_sim_times = []

    for item in items:
        attrs = item.get(
            "attributes",
            {}
        )

        t = attrs.get(
            "source_sim_time"
        )

        if isinstance(
            t,
            (int, float)
        ):
            source_sim_times.append(t)

    sim_time = (
        max(source_sim_times)
        if source_sim_times
        else None
    )

    payload = {
        "t": sim_time,
        "n": nodes,
        "f": flows
    }

    return payload


def send_to_ns3(payload):
    """
    Serialize one complete Ditto snapshot and transmit it as
    multiple application-level UDP chunks.

    Frame format:
        NDT1|snapshot_id|chunk_index|chunk_count|sim_time|<raw bytes>

    Reassembly is performed by the ns-3 DittoControllerApp.
    """

    raw = json.dumps(
        payload,
        separators=(",", ":")
    ).encode("utf-8")

    # Content-derived identifier:
    # identical snapshots obtain the same identifier.
    snapshot_id = hashlib.sha256(
        raw
    ).hexdigest()[:16]

    sim_time = payload.get("t")
    sim_time_field = (
        str(sim_time)
        if sim_time is not None
        else ""
    )

    chunks = [
        raw[i:i + UDP_CHUNK_SIZE]
        for i in range(
            0,
            len(raw),
            UDP_CHUNK_SIZE
        )
    ]

    if not chunks:
        chunks = [b""]

    chunk_count = len(chunks)

    for chunk_index, chunk in enumerate(chunks):
        header = (
            f"NDT1|"
            f"{snapshot_id}|"
            f"{chunk_index}|"
            f"{chunk_count}|"
            f"{sim_time_field}|"
        ).encode("ascii")

        frame_payload = header + chunk

        packet = (
            Ether(
                src=SOURCE_MAC,
                dst=TARGET_MAC
            )
            / IP(
                src=SOURCE_IP,
                dst=TARGET_IP
            )
            / UDP(
                sport=54321,
                dport=TARGET_PORT
            )
            / Raw(
                load=frame_payload
            )
        )

        sendp(
            packet,
            iface=INTERFACE,
            verbose=False
        )

    log(
        f"Sent snapshot {snapshot_id}: "
        f"{len(raw)} bytes in "
        f"{chunk_count} UDP chunk(s), "
        f"max_chunk={UDP_CHUNK_SIZE} bytes"
    )


def content_hash(payload):
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":")
    ).encode("utf-8")

    return hashlib.sha256(
        encoded
    ).hexdigest()


def main():
    log(
        "Ditto -> ns-3 atomic snapshot adapter starting."
    )

    last_sim_time = None
    sent_count = 0

    # Establish the current Ditto state as a baseline.
    # A snapshot left by a previous experiment must not be projected
    # into the new ns-3 run.
    try:
        initial_payload = fetch_atomic_snapshot()
        last_sim_time = initial_payload.get("t")

        if last_sim_time is not None:
            log(
                f"Ignoring pre-existing Ditto snapshot: "
                f"sim_t={last_sim_time}"
            )

    except Exception:
        # It is valid for the aggregate Thing not to exist yet.
        last_sim_time = None

    while True:
        try:
            payload = fetch_atomic_snapshot()

            sim_time = payload.get("t")

            if sim_time is None:
                time.sleep(POLL_INTERVAL)
                continue

            # Exactly one projection per new PT simulation timestamp.
            if sim_time == last_sim_time:
                time.sleep(POLL_INTERVAL)
                continue

            send_to_ns3(
                payload
            )

            sent_count += 1

            log(
                f"Sent to ns-3: "
                f"nodes={len(payload['n'])}, "
                f"flows={len(payload['f'])}, "
                f"sim_t={sim_time}, "
                f"count={sent_count}"
            )

            last_sim_time = sim_time

            time.sleep(
                POLL_INTERVAL
            )

        except KeyboardInterrupt:
            log("Adapter stopped.")
            break

        except Exception as exc:
            log(f"Adapter error: {exc}")
            time.sleep(0.2)


if __name__ == "__main__":
    main()
