#!/usr/bin/env python3

import argparse
import fcntl
import json
import time
from pathlib import Path

from scapy.all import sniff, IP, UDP, Raw


FRAGMENTS = {}
FRAGMENT_TIMEOUT = 5.0


def append_locked(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.write(json.dumps(obj, separators=(",", ":")) + "\n")
        f.flush()
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def write_event(args, payload, payload_bytes, wire_bytes):
    now = time.time()

    row = {
        "event": args.mode,
        "sequence": payload.get(
            "sequence",
            payload.get("seq")
        ),
        "decision_index": payload.get("decision_index"),
        "frequency_hz": payload.get("frequency_hz"),
        "mask": payload.get("mask"),

        "pt_sim_time": payload.get("t"),
        "generation_wall_time":
            payload.get("pt_generated_wall_time"),

        "payload_bytes": payload_bytes,
        "wire_bytes": wire_bytes,
    }

    if args.mode == "tx":
        row["send_wall_time"] = now
    else:
        row["receive_wall_time"] = now

    append_locked(args.log, row)


def cleanup_fragments():
    now = time.time()

    stale = [
        key
        for key, state in FRAGMENTS.items()
        if now - state["last_seen"] > FRAGMENT_TIMEOUT
    ]

    for key in stale:
        del FRAGMENTS[key]


def process_fragment(pkt, args):
    ip = pkt[IP]

    key = (
        ip.src,
        ip.dst,
        int(ip.id),
        int(ip.proto),
    )

    state = FRAGMENTS.setdefault(
        key,
        {
            "parts": {},
            "wire": {},
            "target": False,
            "last_end": None,
            "last_seen": time.time(),
        }
    )

    state["last_seen"] = time.time()

    offset = int(ip.frag) * 8

    fragment_payload = bytes(ip.payload)

    state["parts"][offset] = fragment_payload
    state["wire"][offset] = len(bytes(pkt))

    # First fragment contains the UDP header.
    if offset == 0 and UDP in pkt:
        udp = pkt[UDP]

        if udp.sport == args.port or udp.dport == args.port:
            state["target"] = True

    # MF=0 means this is the final fragment.
    if not bool(ip.flags.MF):
        state["last_end"] = (
            offset + len(fragment_payload)
        )

    if not state["target"]:
        return

    if state["last_end"] is None:
        return

    # Verify that all fragment ranges are contiguous.
    expected = 0
    assembled = bytearray()

    for off in sorted(state["parts"]):
        data = state["parts"][off]

        if off != expected:
            return

        assembled.extend(data)
        expected += len(data)

    if expected != state["last_end"]:
        return

    # Complete IPv4 payload =
    # UDP header (8 bytes) + JSON synchronization payload.
    if len(assembled) <= 8:
        del FRAGMENTS[key]
        return

    udp_payload = bytes(assembled[8:])

    try:
        payload = json.loads(
            udp_payload.decode("utf-8")
        )
    except Exception:
        del FRAGMENTS[key]
        return

    actual_wire_bytes = sum(
        state["wire"].values()
    )

    write_event(
        args,
        payload,
        len(udp_payload),
        actual_wire_bytes
    )

    del FRAGMENTS[key]


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument(
        "--mode",
        choices=["tx", "rx"],
        required=True
    )

    ap.add_argument(
        "--iface",
        default="eth0"
    )

    ap.add_argument(
        "--port",
        type=int,
        default=9999
    )

    ap.add_argument(
        "--log",
        required=True
    )

    args = ap.parse_args()

    print(
        f"[sniffer-{args.mode}] "
        f"iface={args.iface} port={args.port}",
        flush=True
    )

    def handle(pkt):
        cleanup_fragments()

        if IP not in pkt:
            return

        ip = pkt[IP]

        fragmented = (
            bool(ip.flags.MF)
            or int(ip.frag) > 0
        )

        if fragmented:
            process_fragment(pkt, args)
            return

        # Normal non-fragmented UDP message.
        if UDP not in pkt or Raw not in pkt:
            return

        udp = pkt[UDP]

        if (
            udp.sport != args.port
            and udp.dport != args.port
        ):
            return

        raw = bytes(pkt[Raw].load)

        try:
            payload = json.loads(
                raw.decode("utf-8")
            )
        except Exception:
            return

        write_event(
            args,
            payload,
            len(raw),
            len(bytes(pkt))
        )

    # IMPORTANT:
    # Do not use "udp port 9999" here.
    # Later IP fragments do not contain a UDP header and
    # would be discarded before reassembly.
    sniff(
        iface=args.iface,
        filter="ip",
        store=False,
        prn=handle,
    )


if __name__ == "__main__":
    main()
