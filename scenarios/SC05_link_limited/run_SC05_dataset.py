#!/usr/bin/env python3
import argparse, json, os, shutil, subprocess, sys, time, shlex
from pathlib import Path

HOME=Path.home()
ROOT=HOME/"omnet/NDT_journal"
SC=ROOT/"scenarios/SC05_link_limited"
COMMON=ROOT/"scripts/common"

def core_node_command(session_id, node_id, command):
    shell_command = "bash -lc " + shlex.quote(command)

    code = f"""from core.api.grpc import client
c = client.CoreGrpcClient()
c.connect()
print(c.node_command({session_id}, {node_id}, {shell_command!r}))
"""

    return subprocess.run(
        ["core-python", "-c", code],
        text=True,
        capture_output=True
    )


def ns3_log_is_clean(ns3_log_path):
    bad_patterns = [
        "NS_ASSERT",
        "NS_FATAL",
        "terminate called",
        "Segmentation",
        "Aborted",
    ]

    try:
        txt = Path(ns3_log_path).read_text(errors="ignore")
    except Exception:
        return False

    return not any(p in txt for p in bad_patterns)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--seed",type=int,required=True)
    ap.add_argument("--duration",type=int,default=600)
    ap.add_argument("--core-scenario", type=str,
                    default=str(ROOT/"core_profiles/C0_clean.py"))
    ap.add_argument("--core-profile", type=str,
                    default=str(ROOT/"core_profiles/C0_clean_profile.py"))
    ap.add_argument("--link-label", type=str, default="C0")
    a=ap.parse_args()

    out=SC/"results"/f"seed_{a.seed}"
    if out.exists():
        shutil.rmtree(out)
    for d in ["raw","observations","fidelity","dataset","summary","logs"]:
        (out/d).mkdir(parents=True,exist_ok=True)

    actions=out/"raw/actions.jsonl"
    sync_log=out/"raw/sync_messages.jsonl"
    comm_log=out/"raw/communication_metrics.jsonl"
    sync_log.touch()
    comm_log.touch()

    # Bootstrap action before the sender starts.
    initial={
        "wall_time":time.time(),
        "decision_index":-1,
        "sequence":-1,
        "frequency_hz":10,
        "mask":"MT",
        "pt_sampling_hz":10,
        "behavior_policy":"bootstrap",
        "seed":a.seed
    }
    Path("/tmp/ndt_action_control.json").write_text(json.dumps(initial)+"\n")
    Path("/tmp/ndt_pt_sampling_hz").write_text("10\n")

    env=os.environ.copy()
    env.update({
        "SIM_DURATION":str(a.duration+15),
        "SYNC_HZ":"10",
        "SYNC_MASK":"MT",
        "PT_SAMPLING_INTERVAL":"0.1s",
        "OMNET_INI":str(SC/"config/omnetpp_SC05.ini"),
        "OMNET_CONFIG":"SC05",
        "CORE_SCENARIO":a.core_scenario,
        "CORE_PROFILE":a.core_profile,
        "NDT_RUN_DIR":str(out),
        "NDT_SEED":str(a.seed),
        "NDT_NUM_UES":"20",
        "NDT_NUM_GNBS":"2"
    })

    print(f"[SC05] seed={a.seed} duration={a.duration}s",flush=True)
    print("[SC05] starting canonical pipeline...",flush=True)

    with (out/"logs/pipeline.log").open("w") as log:
        r=subprocess.run(
            ["bash",str(HOME/"run_ndt_bus_1h.sh")],
            env=env,stdout=log,stderr=subprocess.STDOUT
        )
    if r.returncode!=0:
        raise SystemExit("Pipeline startup failed. Check logs/pipeline.log")

    sid=int(Path("/tmp/ndt_core_session_id").read_text().strip())

    # Start real packet capture on PT and DT CORE interfaces.
    sniffer=COMMON/"sync_packet_sniffer.py"
    tx_cmd=f"nohup python3 -u {sniffer} --mode tx --iface eth0 --port 9999 --log {sync_log} > {out/'logs/sync_tx.log'} 2>&1 &"
    rx_cmd=f"nohup python3 -u {sniffer} --mode rx --iface eth0 --port 9999 --log {sync_log} > {out/'logs/sync_rx.log'} 2>&1 &"
    core_node_command(sid,2,tx_cmd)
    core_node_command(sid,3,rx_cmd)
    time.sleep(1)

    procs=[]

    def spawn(cmd,logname):
        fh=(out/"logs"/logname).open("w")
        proc=subprocess.Popen(cmd,stdout=fh,stderr=subprocess.STDOUT)
        procs.append((proc,fh))
        return proc

    scheduler=spawn([
        sys.executable,"-u",str(COMMON/"balanced_action_scheduler.py"),
        "--duration",str(a.duration),
        "--interval","2",
        "--seed",str(a.seed),
        "--actions-log",str(actions)
    ],"actions.log")

    comm=spawn([
        "core-python","-u",str(COMMON/"communication_monitor.py"),
        "--session-id",str(sid),
        "--duration",str(a.duration),
        "--interval","2",
        "--sync-log",str(sync_log),
        "--out",str(comm_log)
    ],"communication_monitor.log")

    collector=spawn([
        sys.executable,"-u",str(COMMON/"collect_ndt_global.py"),
        "--pt",str(ROOT/"omnet/FiveG_network/simulations/network_state_latest.json"),
        "--dt",str(HOME/"ns-3-dev/dt_state_latest.json"),
        "--comm",str(comm_log),
        "--sync",str(sync_log),
        "--actions",str(actions),
        "--out",str(out),
        "--duration",str(a.duration),
        "--decision-interval","2",
        "--fidelity-interval","0.5"
    ],"collector.log")

    print("[SC05] collection started",flush=True)

    invalid=False
    while collector.poll() is None:
        time.sleep(2)
        alive=subprocess.run(
            ["bash","-lc","pgrep -f '[F]iveG_digital_twin' >/dev/null"]
        ).returncode==0
        if not alive:
            invalid=True
            print("[SC05] ERROR: ns-3 disappeared before collection ended",flush=True)
            collector.terminate()
            scheduler.terminate()
            comm.terminate()
            break

    for proc,fh in procs:
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.terminate()
        fh.close()

    # Preserve raw PT and DT traces.
    pt=ROOT/"omnet/FiveG_network/simulations/pt_state.jsonl"
    if pt.exists():
        shutil.copy2(pt,out/"raw/pt_state.jsonl")
    # Preserve the current DT state and the complete DT history.
    dt_latest = HOME/"ns-3-dev/dt_state_latest.json"
    if dt_latest.exists():
        shutil.copy2(
            dt_latest,
            out/"raw/dt_state_latest.json"
        )

    dt_history = HOME/"ns-3-dev/dt_state_history.jsonl"
    if dt_history.exists():
        shutil.copy2(
            dt_history,
            out/"raw/dt_state_history.jsonl"
        )

    # Final integrity validation
    expected_decisions = int(a.duration / 2.0)
    expected_fidelity = int(a.duration / 0.5)

    def count_lines(path):
        try:
            with open(path, "r") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0

    action_count = count_lines(out/"raw/actions.jsonl")
    decision_count = count_lines(out/"observations/decision_observations.jsonl")
    fidelity_count = count_lines(out/"fidelity/fidelity_timeseries.jsonl")
    comm_count = count_lines(out/"raw/communication_metrics.jsonl")

    # Resolve the experiment directory used by this run
    exp_dir = None
    try:
        pipeline_log = (out/"logs/pipeline.log").read_text(errors="ignore")
        import re
        m = re.search(
            r"/home/abdessamedseddiki/ndt_experiments/bus_1h_[0-9_]+",
            pipeline_log
        )
        if m:
            exp_dir = Path(m.group(0))
    except Exception:
        pass

    ns3_log = exp_dir/"ns3.log" if exp_dir else None
    ns3_ok = bool(
        ns3_log
        and ns3_log.exists()
        and ns3_log_is_clean(ns3_log)
    )

    counts_ok = (
        action_count == expected_decisions
        and decision_count == expected_decisions
        and fidelity_count == expected_fidelity
        and comm_count == expected_decisions
    )

    final_valid = (
        not invalid
        and counts_ok
        and ns3_ok
    )

    summary={
        "scenario":"SC05",
        "link_profile":a.link_label,
        "seed":a.seed,
        "duration_s":a.duration,
        "decision_interval_s":2.0,
        "fidelity_interval_s":0.5,
        "behavior_policy":"balanced_shuffled_21_actions",
        "frequencies_hz":[1,2,5,10,20,30,50],
        "masks":["M","T","MT"],
        "counts":{
            "actions":action_count,
            "decisions":decision_count,
            "fidelity":fidelity_count,
            "communication":comm_count
        },
        "ns3_log_clean":ns3_ok,
        "runtime_watchdog_ok":not invalid,
        "valid":final_valid
    }

    (out/"summary/run_summary.json").write_text(
        json.dumps(summary,indent=2)+"\n"
    )

    print(
        "[SC05]",
        "VALID" if final_valid else "INVALID",
        flush=True
    )

if __name__=="__main__":
    main()
