#!/usr/bin/env python3
import json, os, socket, time
from pathlib import Path

STATE_FILE=Path(os.environ.get(
    "NDT_STATE_FILE",
    "/home/abdessamedseddiki/omnet/NDT_journal/omnet/FiveG_network/simulations/network_state_latest.json"
))
CONTROL_FILE=Path(os.environ.get("NDT_ACTION_CONTROL","/tmp/ndt_action_control.json"))

SRC_IP=os.environ.get("NDT_SOURCE_IP","10.100.0.2")
DST_IP=os.environ.get("NDT_DEST_IP","10.100.0.3")
DST_PORT=int(os.environ.get("NDT_DEST_PORT","9999"))
POLL=float(os.environ.get("NDT_SENDER_POLL","0.005"))

DEFAULT_HZ=float(os.environ.get("NDT_SYNC_HZ","10"))
DEFAULT_MASK=os.environ.get("NDT_SYNC_MASK","MT").upper()

def read_json(path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None

def read_control():
    x=read_json(CONTROL_FILE) or {}
    try:
        hz=float(x.get("frequency_hz",DEFAULT_HZ))
    except Exception:
        hz=DEFAULT_HZ
    mask=str(x.get("mask",DEFAULT_MASK)).upper()
    if mask not in {"M","T","MT"}:
        mask=DEFAULT_MASK
    return {
        **x,
        "frequency_hz":max(0.1,hz),
        "mask":mask,
        "decision_index":int(x.get("decision_index",-1))
    }

def compact_node(n):
    return {
        "id":n.get("id"),
        "x":n.get("x",0.0),
        "y":n.get("y",0.0),
        "z":n.get("z",0.0),
        "speed":n.get("speed",0.0)
    }

def compact_flow(f):
    return {
        "s":f.get("src"),
        "d":f.get("dst"),
        "sz":f.get("packet_size"),
        "i":f.get("interval"),
        "or":f.get("offered_rate_bps")
    }

def main():
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:
        sock.bind((SRC_IP,0))
    except OSError:
        pass

    seq=0
    last_send_wall=0.0
    last_state_t=None

    print("OMNeT -> CORE/EMANE dynamic sender started",flush=True)
    print(f"State file : {STATE_FILE}",flush=True)
    print(f"Control    : {CONTROL_FILE}",flush=True)
    print(f"Destination: {DST_IP}:{DST_PORT}",flush=True)

    while True:
        ctrl=read_control()
        hz=float(ctrl["frequency_hz"])
        mask=ctrl["mask"]
        period=1.0/hz
        now=time.time()

        if now-last_send_wall<period:
            time.sleep(POLL)
            continue

        state=read_json(STATE_FILE)
        if not isinstance(state,dict) or state.get("timestamp") is None:
            time.sleep(POLL)
            continue

        state_t=state.get("timestamp")
        if state_t==last_state_t:
            time.sleep(POLL)
            continue

        effective_mask="MT" if seq==0 else mask

        payload={
            "seq":seq,
            "sequence":seq,
            "t":state_t,
            "pt_generated_wall_time":state.get("generated_wall_time"),
            "sender_send_wall_time":now,
            "decision_index":ctrl.get("decision_index",-1),
            "frequency_hz":hz,
            "mask":effective_mask,
            "n":[],
            "f":[]
        }

        if "M" in effective_mask:
            payload["n"]=[compact_node(n) for n in state.get("nodes",[])]

        if "T" in effective_mask:
            payload["f"]=[compact_flow(f) for f in state.get("flows",[])]

        raw=json.dumps(payload,separators=(",",":")).encode("utf-8")
        sock.sendto(raw,(DST_IP,DST_PORT))

        last_send_wall=now
        last_state_t=state_t

        if seq%max(1,int(hz*10))==0:
            print(
                f"seq={seq} sim_time={state_t} bytes={len(raw)} "
                f"action={hz:g}Hz/{effective_mask} "
                f"nodes={len(payload['n'])} flows={len(payload['f'])}",
                flush=True
            )
        seq+=1

if __name__=="__main__":
    main()
