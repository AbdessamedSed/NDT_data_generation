import json
import math
from pathlib import Path
from bisect import bisect_right
from statistics import mean

ROOT = Path.home() / "ndt_what_final"

MODES = ("M", "T", "MT")


def load_pt(path):
    return [
        json.loads(x)
        for x in path.read_text().splitlines()
        if x.strip()
    ]


def load_dt(path):
    return json.loads(path.read_text())


def clean_id(x):
    x = str(x)

    # Remove namespace if present.
    if ":" in x:
        x = x.split(":")[-1]

    # Normalize OMNeT++ vector-style UE names:
    # ue[0] -> ue0
    # ue[1] -> ue1
    x = x.replace("[", "").replace("]", "")

    # Normalize possible Physical-Twin / Digital-Twin server naming.
    if x in ("remoteHost", "server"):
        x = "server"

    return x


def percentile(vals, q):
    if not vals:
        return float("nan")
    vals = sorted(vals)
    p = (len(vals) - 1) * q
    lo = int(math.floor(p))
    hi = int(math.ceil(p))
    if lo == hi:
        return vals[lo]
    a = p - lo
    return vals[lo] * (1 - a) + vals[hi] * a


def node_map(row):
    return {
        clean_id(n.get("id")): n
        for n in row.get("nodes", [])
        if n.get("id")
    }


def flow_map(row):
    out = {}
    for f in row.get("flows", []):
        src = clean_id(f.get("src", ""))
        dst = clean_id(f.get("dst", ""))
        if src and dst:
            out[(src, dst)] = f
    return out


def latest_pt(pt, walls, wall):
    i = bisect_right(walls, wall) - 1
    return None if i < 0 else pt[i]


def get_sinr(n):
    try:
        v = float(n.get("sinr_dl", -999))
        if math.isfinite(v) and v > -100:
            return v
    except Exception:
        pass
    return None


def get_thr(f):
    try:
        v = float(f.get("rlc_throughput_Bps"))
        if math.isfinite(v):
            return v
    except Exception:
        pass
    return None


summary = {}

for mode in MODES:

    folder = ROOT / mode

    pt = load_pt(folder / "pt_state.jsonl")
    dt = load_dt(folder / "dt_state.json")

    pt.sort(
        key=lambda x: float(x["generated_wall_time"])
    )

    pt_walls = [
        float(x["generated_wall_time"])
        for x in pt
    ]

    aoi_m = []
    aoi_t = []
    pos_err = []
    sinr_err = []
    thr_err = []
    t_mismatch = []

    for d in dt:

        wall = d.get("wall_time")
        if wall is None:
            continue

        wall = float(wall)

        if wall < pt_walls[0] or wall > pt_walls[-1]:
            continue

        p = latest_pt(pt, pt_walls, wall)

        if p is None:
            continue

        pt_now = float(p["timestamp"])

        src_m = float(
            d.get("source_sim_time_M", -1)
        )

        src_t = float(
            d.get("source_sim_time_T", -1)
        )

        if src_m >= 0:
            aoi_m.append(
                max(0.0, pt_now - src_m)
            )

        if src_t >= 0:
            aoi_t.append(
                max(0.0, pt_now - src_t)
            )

        pn = node_map(p)
        dn = node_map(d)

        for nid in set(pn) & set(dn):

            if nid.lower().startswith("gnb"):
                continue

            a = pn[nid]
            b = dn[nid]

            try:
                dx = float(a["x"]) - float(b["x"])
                dy = float(a["y"]) - float(b["y"])
                dz = float(a.get("z", 0)) - float(b.get("z", 0))

                pos_err.append(
                    math.sqrt(dx*dx + dy*dy + dz*dz)
                )
            except Exception:
                pass

            sa = get_sinr(a)
            sb = get_sinr(b)

            if sa is not None and sb is not None:
                sinr_err.append(abs(sa - sb))

        pf = flow_map(p)
        df = flow_map(d)

        if pf:
            mismatch = 0
            compared = 0

            for key, fp in pf.items():
                compared += 1

                if key not in df:
                    mismatch += 1
                    continue

                fd = df[key]

                try:
                    psz = int(fp["packet_size"])
                    dsz = int(fd["packet_size"])

                    pint = float(fp["interval"])
                    dint = float(fd["interval"])

                    if (
                        psz != dsz
                        or abs(pint - dint) > 1e-9
                    ):
                        mismatch += 1
                except Exception:
                    mismatch += 1

                pt_thr = get_thr(fp)
                dt_thr = get_thr(fd)

                if pt_thr is not None and dt_thr is not None:
                    thr_err.append(
                        abs(pt_thr - dt_thr)
                    )

            if compared:
                t_mismatch.append(
                    mismatch / compared
                )

    # ns-3 real-time behavior.
    valid_dt = [
        r for r in dt
        if r.get("wall_time") is not None
    ]

    ns3_sim_span = (
        float(valid_dt[-1]["timestamp"])
        - float(valid_dt[0]["timestamp"])
    )

    ns3_wall_span = (
        float(valid_dt[-1]["wall_time"])
        - float(valid_dt[0]["wall_time"])
    )

    ns3_rate = (
        ns3_sim_span / ns3_wall_span
        if ns3_wall_span > 0 else float("nan")
    )

    summary[mode] = {
        "aoi_m_mean": mean(aoi_m) if aoi_m else None,
        "aoi_m_p95": percentile(aoi_m, .95) if aoi_m else None,
        "aoi_m_max": max(aoi_m) if aoi_m else None,

        "aoi_t_mean": mean(aoi_t) if aoi_t else None,
        "aoi_t_p95": percentile(aoi_t, .95) if aoi_t else None,
        "aoi_t_max": max(aoi_t) if aoi_t else None,

        "position_mean": mean(pos_err) if pos_err else None,
        "sinr_mean": mean(sinr_err) if sinr_err else None,
        "throughput_mean": mean(thr_err) if thr_err else None,

        "traffic_mismatch":
            mean(t_mismatch) if t_mismatch else None,

        "ns3_rate": ns3_rate,
    }


def fmt(v, digits=3):
    if v is None:
        return "N/A"
    return f"{v:.{digits}f}"


print()
print("=" * 100)
print("FINAL WHAT-TO-SYNCHRONIZE PILOT")
print("=" * 100)

print(
    f"{'Mode':<5}"
    f"{'AoI_M':>10}"
    f"{'AoI_T':>10}"
    f"{'Pos(m)':>12}"
    f"{'SINR(dB)':>12}"
    f"{'Thr(B/s)':>14}"
    f"{'Tmis(%)':>12}"
    f"{'ns3 rate':>12}"
)

for mode in MODES:
    x = summary[mode]

    print(
        f"{mode:<5}"
        f"{fmt(x['aoi_m_mean']):>10}"
        f"{fmt(x['aoi_t_mean']):>10}"
        f"{fmt(x['position_mean']):>12}"
        f"{fmt(x['sinr_mean']):>12}"
        f"{fmt(x['throughput_mean'],1):>14}"
        f"{fmt(None if x['traffic_mismatch'] is None else 100*x['traffic_mismatch'],2):>12}"
        f"{fmt(x['ns3_rate'],3):>12}"
    )

print()
print("AoI P95 / MAX")

for mode in MODES:
    x = summary[mode]

    print(
        f"{mode}: "
        f"M mean/p95/max="
        f"{fmt(x['aoi_m_mean'])}/"
        f"{fmt(x['aoi_m_p95'])}/"
        f"{fmt(x['aoi_m_max'])} s | "
        f"T mean/p95/max="
        f"{fmt(x['aoi_t_mean'])}/"
        f"{fmt(x['aoi_t_p95'])}/"
        f"{fmt(x['aoi_t_max'])} s"
    )

out = ROOT / "what_final_summary.json"
out.write_text(
    json.dumps(summary, indent=2)
)

print("\nSaved:", out)
