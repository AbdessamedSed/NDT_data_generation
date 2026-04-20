import socket
import json
import os
import time
import subprocess
import sys

# to run this: sudo ip netns exec ns-omnet python3 omnetpp_ditto_sender.py


# --- CONFIGURATION ---
GLOBAL_FREQ = 10 # Hz (À faire varier pour tes tests RL)
UDP_IP_DEST = "10.255.0.1"   # IP du PC (Hôte)
UDP_IP_SRC = "10.255.0.10"   # IP dans le Namespace
UDP_PORT = 9999
INTERFACE = "veth-sender"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(SCRIPT_DIR, "..", "simulations", "network_state.json")
SENT_LOG_PATH = os.path.join(SCRIPT_DIR, "sent_packet_ids.txt")

NETWORK_PROFILES = {
    "1": {"desc": "Fibre (Idéal)", "delay": "1ms", "loss": "0%", "rate": "1000mbit", "corrupt": "0.1%"},
    "2": {"desc": "5G URLLC", "delay": "5ms", "loss": "0.001%", "rate": "500mbit", "corrupt": "0.1%"},
    "3": {"desc": "5G eMBB", "delay": "20ms", "loss": "4%", "rate": "100mbit", "corrupt": "5%"},
    "4": {"desc": "4G LTE", "delay": "50ms", "loss": "4%", "rate": "20mbit", "corrupt": "10%"},
    "5": {"desc": "Satellite", "delay": "150ms", "loss": "10%", "rate": "10mbit", "corrupt": "20%"},
    "6": {"desc": "Congestion", "delay": "300ms", "loss": "15%", "rate": "2mbit", "corrupt": "30%"}
}

def apply_network_conditions(config):
    print(f"\n[TC] Configuration : {config['desc']}")
    subprocess.run(f"tc qdisc del dev {INTERFACE} root 2>/dev/null || true", shell=True)
    cmd = f"tc qdisc add dev {INTERFACE} root netem delay {config['delay']} loss {config['loss']} rate {config['rate']}"
    if config.get("corrupt") and config["corrupt"] != "0%":
        cmd += f" corrupt {config['corrupt']}"
    subprocess.run(cmd, shell=True)
    print(f"[TC] Commande appliquée : {cmd}")

def main():
    if os.getuid() != 0:
        print("Erreur: Doit être lancé avec sudo (via ip netns exec)"); sys.exit(1)

    # Init Log
    with open(SENT_LOG_PATH, "w") as f:
        f.write("SnapshotID\tTimestampMS\tSimTime\tStatus\n")

    print("\n" + "="*40)
    for k, v in NETWORK_PROFILES.items(): print(f" {k}. {v['desc']}")
    choice = input("\nChoix du profil : ")
    if choice in NETWORK_PROFILES:
        apply_network_conditions(NETWORK_PROFILES[choice])
    else: print("Choix invalide"); return

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP_SRC, 0))
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, INTERFACE.encode())

    snapshot_id = 0
    print(f"[*] Envoi via {INTERFACE} vers {UDP_IP_DEST}...")

    try:
        while True:
            start_time = time.time()
            if os.path.exists(JSON_PATH):
                try:
                    with open(JSON_PATH, "r") as f:
                        data = json.load(f)
                        # On prend le dernier état du tableau
                        last_state = data[-1] if isinstance(data, list) else data
                        
                        snapshot_id += 1
                        packet = {
                            "snapshot_id": snapshot_id,
                            "sim_time": last_state.get("timestamp", 0),
                            "nodes": last_state.get("nodes", []),
                            "flows": last_state.get("flows", [])
                        }
                        
                        msg = json.dumps(packet).encode()
                        sock.sendto(msg, (UDP_IP_DEST, UDP_PORT))
                        
                        # Logging
                        ts_ms = int(time.time() * 1000)
                        with open(SENT_LOG_PATH, "a") as log_f:
                            log_f.write(f"{snapshot_id}\t{ts_ms}\t{packet['sim_time']}\tSENT\n")
                        
                        print(f" [TX] #{snapshot_id} envoyé (SimTime: {packet['sim_time']}s)")
                except Exception as e:
                    print(f"Erreur lecture/envoi: {e}")

            elapsed = time.time() - start_time
            sleep_time = (1.0 / GLOBAL_FREQ) - elapsed
            if sleep_time > 0: time.sleep(sleep_time)
    except KeyboardInterrupt:
        print("\nArrêt Sender.")

if __name__ == "__main__":
    main()