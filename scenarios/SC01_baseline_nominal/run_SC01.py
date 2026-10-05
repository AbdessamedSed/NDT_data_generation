#!/usr/bin/env python3
"""
Generic NDT scenario launcher.

It prepares the run folder, starts the global collector, and delegates the
actual NDT component startup order to the already validated canonical launcher:

CORE/EMANE -> Ditto ingress -> ns-3 ready -> Ditto/ns-3 adapter
-> sender -> OMNeT++.

For SC01:
- 600 s
- 1 gNB / 10 UEs
- decision interval 2 s
- fidelity logging 0.5 s
- sync action supplied through --sync-hz and --sync-mask

IMPORTANT:
The existing ~/run_ndt_bus_1h.sh must accept/use these environment variables:
  SIM_DURATION
  SYNC_HZ
  SYNC_MASK
  OMNET_INI
  OMNET_CONFIG
  NDT_RUN_DIR
  NDT_SEED
If OMNET_INI/OMNET_CONFIG are not yet consumed by that shell launcher,
add them there before final dataset runs.
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path


HOME = Path.home()
ROOT = HOME / "omnet" / "NDT_journal"

DEFAULTS = {
    "scenario": "SC01",
    "duration": 600,
    "seed": 101,
    "sync_hz": 10.0,
    "sync_mask": "MT",
}


def mkdirs(out):
    for rel in (
        "raw",
        "observations",
        "fidelity",
        "dataset",
        "summary",
        "logs",
    ):
        (out / rel).mkdir(parents=True, exist_ok=True)


def append_jsonl(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(obj, separators=(",", ":")) + "\n")


def main():
    ap = argparse.ArgumentParser()

    ap.add_argument("--scenario", default=DEFAULTS["scenario"])
    ap.add_argument("--duration", type=int, default=DEFAULTS["duration"])
    ap.add_argument("--seed", type=int, default=DEFAULTS["seed"])
    ap.add_argument("--sync-hz", type=float, default=DEFAULTS["sync_hz"])
    ap.add_argument("--sync-mask", choices=["M", "T", "MT"],
                    default=DEFAULTS["sync_mask"])

    ap.add_argument(
        "--ini",
        default=str(ROOT / "scenarios" / "SC01_baseline_nominal" /
                    "config" / "omnetpp_SC01.ini")
    )
    ap.add_argument("--omnet-config", default="SC01")

    ap.add_argument(
        "--canonical-launcher",
        default=str(HOME / "run_ndt_bus_1h.sh")
    )
    ap.add_argument(
        "--collector",
        default=str(ROOT / "scripts" / "common" /
                    "collect_ndt_global.py")
    )

    args = ap.parse_args()

    scenario_dir = ROOT / "scenarios" / "SC01_baseline_nominal"
    out = scenario_dir / "results" / f"seed_{args.seed}"

    if out.exists():
        shutil.rmtree(out)
    mkdirs(out)

    # Files produced/read during the run.
    pt_latest = ROOT / "omnet" / "FiveG_network" / "simulations" / \
                "network_state_latest.json"
    dt_latest = HOME / "ns-3-dev" / "dt_state.json"

    comm_file = out / "raw" / "communication_metrics.jsonl"
    sync_file = out / "raw" / "sync_messages.jsonl"
    actions_file = out / "raw" / "actions.jsonl"

    comm_file.touch()
    sync_file.touch()

    # Record initial/current synchronization action.
    append_jsonl(actions_file, {
        "wall_time": time.time(),
        "decision_index": 0,
        "sequence": 0,
        "frequency_hz": args.sync_hz,
        "mask": args.sync_mask,
        "seed": args.seed,
    })

    # Dynamic PT acquisition rule agreed for the journal:
    # <=10 Hz -> 10 Hz PT collection
    # >10 Hz  -> PT collection equals selected synchronization rate
    pt_sampling_hz = max(10.0, args.sync_hz)
    pt_sampling_interval = 1.0 / pt_sampling_hz
    pt_sampling_interval = 1.0 / pt_sampling_hz

    env = os.environ.copy()
    env.update({
        "SIM_DURATION": str(args.duration),
        "SYNC_HZ": str(args.sync_hz),
        "SYNC_MASK": args.sync_mask,

        "PT_SAMPLING_HZ": str(pt_sampling_hz),
        "PT_SAMPLING_INTERVAL": f"{pt_sampling_interval}s",
        "PT_SAMPLING_INTERVAL": f"{pt_sampling_interval}s",

        "OMNET_INI": str(Path(args.ini).resolve()),
        "OMNET_CONFIG": args.omnet_config,

        "NDT_RUN_DIR": str(out),
        "NDT_SEED": str(args.seed),

        "CORE_SCENARIO": str(
            ROOT / "core_profiles" / "C0_clean.py"
        ),
        "CORE_PROFILE": str(
            ROOT / "core_profiles" / "C0_clean_profile.py"
        ),

        # Expected logger destinations.
        "NDT_COMM_LOG": str(comm_file),
        "NDT_SYNC_LOG": str(sync_file),
        "NDT_ACTION_LOG": str(actions_file),
    })

    collector_cmd = [
        sys.executable,
        args.collector,
        "--pt", str(pt_latest),
        "--dt", str(dt_latest),
        "--comm", str(comm_file),
        "--sync", str(sync_file),
        "--actions", str(actions_file),
        "--out", str(out),
        "--duration", str(args.duration),
        "--decision-interval", "2.0",
        "--fidelity-interval", "0.5",
    ]

    print("=" * 72)
    print(f"Scenario       : {args.scenario}")
    print(f"Seed           : {args.seed}")
    print(f"Duration       : {args.duration} s")
    print(f"Sync action    : {args.sync_hz} Hz / {args.sync_mask}")
    print(f"PT sampling    : {pt_sampling_hz} Hz")
    print(f"OMNeT ini      : {args.ini}")
    print(f"Output         : {out}")
    print("=" * 72)

    collector_log = (out / "logs" / "collector.log").open("w")
    pipeline_log = (out / "logs" / "pipeline.log").open("w")

    collector_proc = subprocess.Popen(
        collector_cmd,
        env=env,
        stdout=collector_log,
        stderr=subprocess.STDOUT,
    )

    # Small head start so wall-clock collection is already active.
    time.sleep(0.5)

    # The canonical launcher already contains the validated startup order:
    # CORE -> ingress -> ns3 ready -> adapter -> sender -> OMNeT.
    pipeline_proc = subprocess.Popen(
        ["bash", args.canonical_launcher],
        env=env,
        stdout=pipeline_log,
        stderr=subprocess.STDOUT,
    )

    try:
        rc = pipeline_proc.wait()

        # Allow final state files to be observed.
        time.sleep(1.0)

        if collector_proc.poll() is None:
            collector_proc.wait(timeout=max(5, args.duration + 10))

    except KeyboardInterrupt:
        print("\nInterrupted: stopping pipeline and collector...")
        for p in (pipeline_proc, collector_proc):
            if p.poll() is None:
                p.send_signal(signal.SIGINT)
        time.sleep(1)
        for p in (pipeline_proc, collector_proc):
            if p.poll() is None:
                p.terminate()
        rc = 130

    finally:
        collector_log.close()
        pipeline_log.close()

    # Preserve current raw PT/DT histories when they exist.
    raw_pt = ROOT / "omnet" / "FiveG_network" / "simulations" / "pt_state.jsonl"
    raw_dt = HOME / "ns-3-dev" / "dt_state.json"

    if raw_pt.exists():
        shutil.copy2(raw_pt, out / "raw" / "pt_state.jsonl")
    if raw_dt.exists():
        shutil.copy2(raw_dt, out / "raw" / "dt_state_final.json")

    summary = {
        "scenario": args.scenario,
        "seed": args.seed,
        "duration_s": args.duration,
        "sync_hz": args.sync_hz,
        "sync_mask": args.sync_mask,
        "pt_sampling_hz": pt_sampling_hz,
        "pipeline_return_code": rc,
        "output_dir": str(out),
    }

    with (out / "summary" / "run_summary.json").open("w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nRun finished. Results: {out}")
    sys.exit(rc)


if __name__ == "__main__":
    main()
