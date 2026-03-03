from scapy.all import *
import requests, json, time, subprocess, os, sys

DEBUG = True

def dbg(msg):
    if DEBUG:
        print(f"[DEBUG] {msg}")

# ===============================
# SETUP TAP
# ===============================
script = os.path.join(os.path.dirname(__file__), "setup_thetap.sh")
dbg(f"TAP script path: {script}")

if not os.path.isfile(script):
    print("[ERROR] setup_thetap.sh not found")
    sys.exit(1)

dbg("Running setup_thetap.sh")
res = subprocess.run(["sudo", "bash", script], capture_output=True, text=True)
dbg(f"stdout:\n{res.stdout}")
dbg(f"stderr:\n{res.stderr}")
if res.returncode != 0:
    print("[ERROR] setup_thetap.sh failed")
    sys.exit(1)

# ===============================
# CONFIG
# ===============================
iface = "thetap"
src_ip = "10.1.1.10"
src_mac = "00:00:00:00:00:09"
target_ip = "10.1.1.2"
target_mac = "00:00:00:00:00:02"
target_port = 5000

DITTO_URL = "http://localhost:8080/api/2/things"
DITTO_AUTH = ("ditto", "ditto")
INTERVAL = 1

# ===============================
# CHECK INTERFACE
# ===============================
dbg("Available network interfaces:")
dbg(get_if_list())

if iface not in get_if_list():
    print(f"[ERROR] Interface {iface} not found")
    sys.exit(1)

# ===============================
# MAIN LOOP
# ===============================
dbg("Starting main loop")

while True:
    try:
        dbg("Requesting Ditto")
        r = requests.get(DITTO_URL, auth=DITTO_AUTH, timeout=2)
        dbg(f"HTTP status: {r.status_code}")

        if r.status_code != 200:
            time.sleep(INTERVAL)
            continue

        data = r.json()
        payload = json.dumps(data)
        dbg(f"Payload size: {len(payload)} bytes")

        pkt = (
            Ether(src=src_mac, dst=target_mac) /
            IP(src=src_ip, dst=target_ip) /
            UDP(sport=RandShort(), dport=target_port) /
            Raw(load=payload)
        )

        dbg("Sending UDP packet")
        sendp(pkt, iface=iface, verbose=False, promisc=False)
        dbg("Packet sent successfully")

    except Exception as e:
        print(f"[ERROR] {e}")

    time.sleep(INTERVAL)
