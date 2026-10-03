#!/usr/bin/env python3
import argparse, json, os, random, time
from pathlib import Path

FREQS=[1,2,5,10,20,30,50]
MASKS=["M","T","MT"]
ACTIONS=[(f,m) for f in FREQS for m in MASKS]

def atomic_json(path,obj):
    path=Path(path); tmp=Path(str(path)+".tmp")
    tmp.write_text(json.dumps(obj,separators=(",",":"))+"\n")
    os.replace(tmp,path)

def atomic_text(path,text):
    path=Path(path); tmp=Path(str(path)+".tmp")
    tmp.write_text(text); os.replace(tmp,path)

def append_jsonl(path,obj):
    with Path(path).open("a") as f:
        f.write(json.dumps(obj,separators=(",",":"))+"\n")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--duration",type=float,default=600)
    ap.add_argument("--interval",type=float,default=2.0)
    ap.add_argument("--seed",type=int,required=True)
    ap.add_argument("--actions-log",required=True)
    ap.add_argument("--control-file",default="/tmp/ndt_action_control.json")
    ap.add_argument("--pt-hz-file",default="/tmp/ndt_pt_sampling_hz")
    a=ap.parse_args()

    rng=random.Random(a.seed)
    pool=[]
    d=0
    t0=time.monotonic()

    while time.monotonic()-t0<a.duration:
        if not pool:
            pool=ACTIONS.copy()
            rng.shuffle(pool)

        freq,mask=pool.pop()
        pt_hz=max(10,freq)
        now=time.time()

        row={
            "wall_time":now,
            "decision_index":d,
            "sequence":d,
            "frequency_hz":freq,
            "mask":mask,
            "pt_sampling_hz":pt_hz,
            "behavior_policy":"balanced_shuffled_21_actions",
            "seed":a.seed
        }

        atomic_json(a.control_file,row)
        atomic_text(a.pt_hz_file,f"{pt_hz}\n")
        append_jsonl(a.actions_log,row)

        print(f"[action] d={d:03d} {freq:>2} Hz / {mask:<2} PT={pt_hz} Hz",flush=True)

        d+=1
        wait=d*a.interval-(time.monotonic()-t0)
        if wait>0:
            time.sleep(wait)

    print(f"[action] completed: {d}",flush=True)

if __name__=="__main__":
    main()
