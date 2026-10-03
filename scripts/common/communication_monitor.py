#!/usr/bin/env python3
import argparse,json,re,time,shlex
from pathlib import Path
from core.api.grpc import client


def node_shell(core, session_id, node_id, command):
    wrapped = "bash -lc " + shlex.quote(command)
    return core.node_command(session_id, node_id, wrapped)[1]

def append_jsonl(path,obj):
    with Path(path).open("a") as f:
        f.write(json.dumps(obj,separators=(",",":"))+"\n")

def parse_ping(text):
    loss=avg=jit=None
    m=re.search(r"([\d.]+)% packet loss",text)
    if m:
        loss=float(m.group(1))
    m=re.search(r"=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)\s*ms",text)
    if m:
        avg=float(m.group(2))
        jit=float(m.group(4))
    return loss,avg,jit

def parse_stats(text):
    out={}
    for line in text.splitlines():
        if "=" in line:
            k,v=line.split("=",1)
            try: out[k]=int(v)
            except: pass
    return out

def sync_rx_bytes(path,t0,t1):
    n=payload=wire=0
    p=Path(path)
    if not p.exists():
        return 0,0,0
    for line in p.read_text(errors="ignore").splitlines():
        try:x=json.loads(line)
        except:continue
        if x.get("event")!="rx":
            continue
        ts=x.get("receive_wall_time")
        if ts is None or not(t0<=float(ts)<t1):
            continue
        n+=1
        payload+=int(x.get("payload_bytes",0) or 0)
        wire+=int(x.get("wire_bytes",0) or 0)
    return n,payload,wire

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--session-id",type=int,required=True)
    ap.add_argument("--duration",type=float,default=600)
    ap.add_argument("--interval",type=float,default=2.0)
    ap.add_argument("--sync-log",required=True)
    ap.add_argument("--out",required=True)
    a=ap.parse_args()

    c=client.CoreGrpcClient()
    c.connect()

    stat_cmd='for k in tx_bytes rx_bytes tx_packets rx_packets tx_dropped rx_dropped; do f=/sys/class/net/eth0/statistics/$k; [ -r "$f" ] && echo "$k=$(cat "$f")"; done'
    prev_pt=prev_dt=None
    prev_wall=None
    start=time.monotonic()

    while time.monotonic()-start<a.duration:
        tick=time.time()

        ping=node_shell(c,a.session_id,2,"ping -n -q -c 4 -i 0.15 -W 1 10.100.0.3 2>&1 || true")
        loss,rtt,jit=parse_ping(ping)

        pt=parse_stats(node_shell(c,a.session_id,2,stat_cmd))
        dt=parse_stats(node_shell(c,a.session_id,3,stat_cmd))

        now=time.time()
        dw=None if prev_wall is None else max(1e-9,now-prev_wall)

        def rate(cur,old,key):
            if dw is None or old is None or key not in cur or key not in old:
                return None
            return 8.0*max(0,cur[key]-old[key])/dw/1e6

        n,pb,wb=sync_rx_bytes(a.sync_log,now-a.interval,now)

        row={
            "wall_time":now,
            "interval_s":a.interval,
            "rtt_avg_ms":rtt,
            "jitter_rtt_mdev_ms":jit,
            "packet_loss_pct":loss,
            "sync_goodput_mbps":8.0*pb/a.interval/1e6,
            "sync_wire_rx_mbps":8.0*wb/a.interval/1e6,
            "sync_messages_received":n,
            "pt_iface_tx_mbps":rate(pt,prev_pt,"tx_bytes"),
            "pt_iface_rx_mbps":rate(pt,prev_pt,"rx_bytes"),
            "dt_iface_tx_mbps":rate(dt,prev_dt,"tx_bytes"),
            "dt_iface_rx_mbps":rate(dt,prev_dt,"rx_bytes"),
            "pt_tx_bytes_total":pt.get("tx_bytes"),
            "dt_rx_bytes_total":dt.get("rx_bytes"),
            "pt_tx_dropped_total":pt.get("tx_dropped"),
            "dt_rx_dropped_total":dt.get("rx_dropped")
        }
        append_jsonl(a.out,row)

        prev_pt,prev_dt,prev_wall=pt,dt,now
        time.sleep(max(0.0,a.interval-(time.time()-tick)))

if __name__=="__main__":
    main()
