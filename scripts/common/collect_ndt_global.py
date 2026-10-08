#!/usr/bin/env python3
"""
Global NDT wall-clock collector shared by SC01, SC02, ...

Design:
- NEVER force-align OMNeT++ and ns-3 by internal simulation time.
- At each wall-clock observation instant, read the latest PT, DT,
  communication-network, synchronization-message, and action states.
- Decision observations every 2 s.
- Fidelity monitoring every 0.5 s.
- Keep complete PT/DT snapshots plus detailed per-UE comparisons.
"""

import argparse
import json
import math
import statistics
import time
from pathlib import Path


def read_json(path):
    try:
        p = Path(path)
        if not p.exists() or p.stat().st_size == 0:
            return None
        with p.open() as f:
            x = json.load(f)
        if isinstance(x, list):
            return x[-1] if x else None
        return x
    except Exception:
        return None


def read_last_jsonl(path):
    try:
        p = Path(path)
        if not p.exists() or p.stat().st_size == 0:
            return None
        with p.open() as f:
            rows = f.readlines()
        for line in reversed(rows):
            try:
                return json.loads(line)
            except Exception:
                pass
        return None
    except Exception:
        return None


def latest(path):
    return read_last_jsonl(path) if str(path).endswith(".jsonl") else read_json(path)


def append_jsonl(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(obj, separators=(",", ":"), allow_nan=False) + "\n")


def clean_id(x):
    s = str(x or "").lower()
    s = s.replace("my5gnetwork:", "")
    s = s.replace("[", "").replace("]", "")
    s = s.replace("_", "").replace("-", "")
    return s


def first(d, *keys):
    if not isinstance(d, dict):
        return None
    for k in keys:
        if d.get(k) is not None:
            return d[k]
    return None


def num(x):
    try:
        return float(x)
    except Exception:
        return None


def node_map(snapshot):
    out = {}
    if not snapshot:
        return out
    for n in snapshot.get("nodes", []) or []:
        nid = first(n, "id", "name", "node")
        out[clean_id(nid)] = n
    return out


def pos(n):
    return {
        "x": first(n, "x", "pos_x"),
        "y": first(n, "y", "pos_y"),
        "z": first(n, "z", "pos_z"),
    }


def position_error(a, b):
    pa, pb = pos(a), pos(b)
    vals = []
    for k in ("x", "y", "z"):
        x, y = num(pa[k]), num(pb[k])
        if x is None or y is None:
            return None
        vals.append((x-y)**2)
    return math.sqrt(sum(vals))


def abs_error(a, b):
    a, b = num(a), num(b)
    return None if a is None or b is None else abs(a-b)


def get_speed(n):
    return first(n, "speed", "velocity")


def get_sinr(n):
    return first(n, "sinr_dl", "sinr", "dl_sinr")


def get_thr(n):
    return first(n, "rlc_throughput_dl", "mac_thr_dl",
                 "throughput_dl", "throughput")


def flow_map(snapshot):
    """
    Map each DL flow to its destination UE.

    PT identifiers may use ue[0], while DT identifiers may use ue0.
    clean_id() normalizes both to the same representation.
    """
    out = {}

    if not snapshot:
        return out

    for f in snapshot.get("flows", []) or []:
        dst = first(f, "dst", "destination", "dest")
        if dst is None:
            continue

        uid = clean_id(dst)

        if uid.startswith("ue"):
            out[uid] = f

    return out


def flow_throughput(f):
    return first(
        f,
        "rlc_throughput_Bps",
        "rlc_throughput_dl_Bps",
        "mac_throughput_Bps",
        "throughput_Bps",
        "throughput_dl",
        "throughput"
    )


def compare_ues(pt, dt):
    pm = node_map(pt)
    dm = node_map(dt)

    pf = flow_map(pt)
    df = flow_map(dt)

    rows = []

    # Match UEs available on both sides.
    for uid in sorted(set(pm) & set(dm)):
        if not uid.startswith("ue"):
            continue

        pnode = pm[uid]
        dnode = dm[uid]

        pflow = pf.get(uid, {})
        dflow = df.get(uid, {})

        ps = get_speed(pnode)
        ds = get_speed(dnode)

        psi = get_sinr(pnode)
        dsi = get_sinr(dnode)

        pth = flow_throughput(pflow)
        dth = flow_throughput(dflow)

        p_packet = first(pflow, "packet_size", "packetSize")
        d_packet = first(dflow, "packet_size", "packetSize")

        p_interval = first(pflow, "interval", "send_interval")
        d_interval = first(dflow, "interval", "send_interval")

        p_rate = first(pflow, "offered_rate_bps", "offered_rate")
        d_rate = first(dflow, "offered_rate_bps", "offered_rate")

        rows.append({
            "ue_id": uid,

            # ----------------------------------------------------------
            # Mobility
            # ----------------------------------------------------------
            "pt_position": pos(pnode),
            "dt_position": pos(dnode),
            "position_error_m": position_error(pnode, dnode),

            "pt_speed_mps": ps,
            "dt_speed_mps": ds,
            "speed_abs_error_mps": abs_error(ps, ds),

            # ----------------------------------------------------------
            # Radio
            # ----------------------------------------------------------
            "pt_sinr_dl_db": psi,
            "dt_sinr_dl_db": dsi,
            "sinr_abs_error_db": abs_error(psi, dsi),

            # ----------------------------------------------------------
            # Measured throughput
            # ----------------------------------------------------------
            "pt_rlc_throughput_Bps": pth,
            "dt_rlc_throughput_Bps": dth,
            "throughput_abs_error_Bps": abs_error(pth, dth),

            # ----------------------------------------------------------
            # Traffic configuration
            # ----------------------------------------------------------
            "pt_packet_size_B": p_packet,
            "dt_packet_size_B": d_packet,
            "packet_size_abs_error_B": abs_error(p_packet, d_packet),

            "pt_interval_s": p_interval,
            "dt_interval_s": d_interval,
            "interval_abs_error_s": abs_error(p_interval, d_interval),

            "pt_offered_rate_bps": p_rate,
            "dt_offered_rate_bps": d_rate,
            "offered_rate_abs_error_bps": abs_error(p_rate, d_rate),

            # Complete raw objects retained for future analysis.
            "pt_node_raw": pnode,
            "dt_node_raw": dnode,
            "pt_flow_raw": pflow,
            "dt_flow_raw": dflow,
        })

    return rows


def mean(rows, key):
    vals = [num(r.get(key)) for r in rows]
    vals = [v for v in vals if v is not None]
    return statistics.mean(vals) if vals else None


def pt_sim_time(st):
    return first(st, "timestamp", "sim_time")


def dt_sim_time(st):
    return first(st, "timestamp", "sim_time", "ns3_sim_time")


def source_time(dt, domain):
    if domain == "M":
        return first(dt, "source_sim_time_M", "pt_source_time_M", "source_time_M")
    return first(dt, "source_sim_time_T", "pt_source_time_T", "source_time_T")


def aoi(pt, dt, domain):
    latest_pt = num(pt_sim_time(pt))
    applied = num(source_time(dt, domain))
    if latest_pt is None or applied is None or applied < 0:
        return None
    return max(0.0, latest_pt - applied)


def sync_interval(path, t0, t1, delta_t):
    """
    Aggregate synchronization traffic observed on CORE interfaces.

    TX events are counted by send_wall_time inside [t0,t1).
    RX events are matched using sequence number.

    Communication cost is based on transmitted bytes, therefore
    lost updates still consume communication resources.
    """
    p = Path(path)

    tx = {}
    rx = {}

    if p.exists():
        with p.open() as f:
            for line in f:
                line = line.strip()

                if not line:
                    continue

                try:
                    x = json.loads(line)
                except Exception:
                    continue

                seq = x.get("sequence")

                if seq is None:
                    continue

                event = x.get("event")

                if event == "tx":
                    ts = x.get("send_wall_time")

                    try:
                        ts = float(ts)
                    except Exception:
                        continue

                    if t0 <= ts < t1:
                        tx[seq] = x

                elif event == "rx":
                    rx[seq] = x

    sent = len(tx)

    matched = []

    for seq, tx_row in tx.items():
        rx_row = rx.get(seq)

        if rx_row is not None:
            matched.append((tx_row, rx_row))

    received = len(matched)

    payload_tx = sum(
        int(x.get("payload_bytes", 0) or 0)
        for x in tx.values()
    )

    wire_tx = sum(
        int(x.get("wire_bytes", 0) or 0)
        for x in tx.values()
    )

    payload_rx = sum(
        int(r.get("payload_bytes", 0) or 0)
        for _, r in matched
    )

    wire_rx = sum(
        int(r.get("wire_bytes", 0) or 0)
        for _, r in matched
    )

    delays = []

    for tx_row, rx_row in matched:
        try:
            st = float(tx_row["send_wall_time"])
            rt = float(rx_row["receive_wall_time"])
            delays.append((rt - st) * 1000.0)
        except Exception:
            pass

    delays.sort()

    p95 = None

    if delays:
        idx = max(
            0,
            min(
                len(delays) - 1,
                math.ceil(0.95 * len(delays)) - 1
            )
        )

        p95 = delays[idx]

    return {
        "sync_messages_sent": sent,
        "sync_messages_received": received,
        "sync_messages_lost": max(0, sent - received),

        "payload_bytes_tx": payload_tx,
        "payload_bytes_rx": payload_rx,

        "wire_bytes_tx": wire_tx,
        "wire_bytes_rx": wire_rx,

        "sync_payload_kbps":
            (8.0 * payload_tx / delta_t / 1000.0)
            if delta_t > 0 else None,

        "sync_wire_kbps":
            (8.0 * wire_tx / delta_t / 1000.0)
            if delta_t > 0 else None,

        "delivery_ratio":
            (received / sent)
            if sent > 0 else None,

        "mean_sync_delay_ms":
            statistics.mean(delays)
            if delays else None,

        "p95_sync_delay_ms": p95,
    }


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument("--pt", required=True,
                    help="Latest PT JSON, e.g. network_state_latest.json")
    ap.add_argument("--dt", required=True,
                    help="Latest DT JSON, e.g. ~/ns-3-dev/dt_state.json")
    ap.add_argument("--comm", required=True,
                    help="CORE/EMANE communication_metrics.jsonl")
    ap.add_argument("--sync", required=True,
                    help="sync_messages.jsonl")
    ap.add_argument("--actions", required=True,
                    help="actions.jsonl")
    ap.add_argument("--out", required=True,
                    help="Run output folder")

    ap.add_argument("--duration", type=float, default=600.0)
    ap.add_argument("--decision-interval", type=float, default=2.0)
    ap.add_argument("--fidelity-interval", type=float, default=0.5)

    args = ap.parse_args()

    out = Path(args.out)
    decision_file = out / "observations" / "decision_observations.jsonl"
    fidelity_file = out / "fidelity" / "fidelity_timeseries.jsonl"

    start_mono = time.monotonic()
    next_decision = 0.0
    next_fidelity = 0.0
    decision_index = 0

    prev_wall = None
    prev_ns3_sim = None

    while True:
        elapsed = time.monotonic() - start_mono
        if elapsed >= args.duration:
            break

        wall = time.time()

        # ------------------------------------------------------------------
        # Fidelity monitoring every 0.5 s
        # ------------------------------------------------------------------
        if elapsed >= next_fidelity:
            pt = latest(args.pt)
            dt = latest(args.dt)
            comm = latest(args.comm) or {}
            action = latest(args.actions) or {}
            per_ue = compare_ues(pt, dt)

            append_jsonl(fidelity_file, {
                "wall_time": wall,

                "pt_sim_time": pt_sim_time(pt),
                "ns3_sim_time": dt_sim_time(dt),

                "source_sim_time_M": source_time(dt, "M"),
                "source_sim_time_T": source_time(dt, "T"),

                "aoi_M_s": aoi(pt, dt, "M"),
                "aoi_T_s": aoi(pt, dt, "T"),

                "action": action,
                "communication": comm,

                "per_ue": per_ue,

                "aggregates": {
                    "mean_position_error_m":
                        mean(per_ue, "position_error_m"),
                    "mean_sinr_abs_error_db":
                        mean(per_ue, "sinr_abs_error_db"),
                    "mean_throughput_abs_error":
                        mean(per_ue, "throughput_abs_error_Bps"),
                },

                "pt_state": pt,
                "dt_state": dt,
            })

            next_fidelity += args.fidelity_interval

        # ------------------------------------------------------------------
        # RL observation every 2 s
        # ------------------------------------------------------------------
        if elapsed >= next_decision:
            pt = latest(args.pt)
            dt = latest(args.dt)
            comm = latest(args.comm) or {}
            action = latest(args.actions) or {}
            per_ue = compare_ues(pt, dt)

            ns3_now = num(dt_sim_time(dt))
            r_dt = None

            if (ns3_now is not None and
                prev_ns3_sim is not None and
                prev_wall is not None):

                delta_wall = wall - prev_wall
                if delta_wall > 0:
                    r_dt = max(
                        0.0,
                        (ns3_now-prev_ns3_sim) / delta_wall
                    )

            sync = sync_interval(
                args.sync,
                wall-args.decision_interval,
                wall,
                args.decision_interval
            )

            observation = {
                "decision_index": decision_index,
                "wall_time": wall,
                "decision_interval_s": args.decision_interval,

                "pt_sim_time": pt_sim_time(pt),
                "ns3_sim_time": dt_sim_time(dt),

                "pt_source_time_M_applied_in_dt":
                    source_time(dt, "M"),
                "pt_source_time_T_applied_in_dt":
                    source_time(dt, "T"),

                "aoi_M_s": aoi(pt, dt, "M"),
                "aoi_T_s": aoi(pt, dt, "T"),

                "r_DT": r_dt,

                "action": action,

                # RTT, jitter, loss, goodput, queue metrics, etc.
                "communication": comm,

                # Sent sync traffic / communication cost.
                "synchronization": sync,

                # PT vs DT details for every UE.
                "per_ue": per_ue,

                "aggregates": {
                    "mean_position_error_m":
                        mean(per_ue, "position_error_m"),
                    "mean_sinr_abs_error_db":
                        mean(per_ue, "sinr_abs_error_db"),
                    "mean_throughput_abs_error":
                        mean(per_ue, "throughput_abs_error_Bps"),
                },

                # Preserve complete snapshots used at this wall-clock instant.
                "pt_state": pt,
                "dt_state": dt,
            }

            append_jsonl(decision_file, observation)

            if ns3_now is not None:
                prev_ns3_sim = ns3_now
                prev_wall = wall

            decision_index += 1
            next_decision += args.decision_interval

        time.sleep(0.02)

    print(f"[collector] decision observations: {decision_index}")
    print(f"[collector] {decision_file}")
    print(f"[collector] {fidelity_file}")


if __name__ == "__main__":
    main()
