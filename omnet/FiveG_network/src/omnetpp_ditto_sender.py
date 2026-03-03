import subprocess
import os
import sys
import time
import re
import requests
from typing import Dict
import json
from datetime import datetime

# --- CONFIGURATION GLOBALE ---
GLOBAL_FREQ = 10  # Note: 10k Hz est très élevé pour des requêtes HTTP REST
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Chemin vers le fichier JSON généré par OMNeT++
JSON_FILE_PATH = os.path.join(SCRIPT_DIR, "..", "simulations", "network_state.json")
IDS_LOG_PATH = os.path.join(SCRIPT_DIR, "..", "simulations", "sent_packet_ids.txt")

INTERFACE = "lo"
DITTO_URL = "http://localhost:8080"
DITTO_USER = "ditto"
DITTO_PASSWORD = "ditto"
DITTO_NAMESPACE = "my5GNetwork"

NETWORK_PROFILES = {
    "1": {"name": "1", "params": {"delay": "1ms", "jitter": "0.1ms", "rate": "1000mbit", "loss": "0%"}, "desc": "Filaire ultra-stable"},
    "2": {"name": "2", "params": {"delay": "5ms", "jitter": "0.5ms", "rate": "500mbit", "loss": "0.01%"}, "desc": "Performance optimale (Edge)"},
    "3": {"name": "3", "params": {"delay": "10ms", "jitter": "1ms", "rate": "500mbit", "loss": "0.01%"}, "desc": "5G Charge moyenne"},
    "4": {"name": "4", "params": {"delay": "10ms", "jitter": "1ms", "rate": "100mbit", "loss": "0.01%"}, "desc": "5G Charge moyenne"},
    "5": {"name": "5", "params": {"delay": "15ms", "jitter": "15ms", "rate": "80mbit", "loss": "0.5%"}, "desc": "5G Dégradée"},
    "6": {"name": "6", "params": {"delay": "15ms", "jitter": "2ms", "rate": "80mbit", "loss": "5%"}, "desc": "5G Dégradée (Pertes)"},
    "7": {"name": "7", "params": {"delay": "20ms", "jitter": "10ms", "rate": "100mbit", "loss": "1%"}, "desc": "WiFi classique"},
    "8": {"name": "8", "params": {"delay": "30ms", "jitter": "10ms", "rate": "50mbit", "loss": "1%"}, "desc": "WiFi classique"},
    "9": {"name": "9", "params": {"delay": "25ms", "jitter": "15ms", "rate": "10mbit", "loss": "5%"}, "desc": "WiFi saturé"},
    "10": {"name": "10", "params": {"delay": "45ms", "jitter": "15ms", "rate": "20mbit", "loss": "0.5%"}, "desc": "Réseau mobile LD"},
    "11": {"name": "11", "params": {"delay": "500ms", "jitter": "1ms", "rate": "128kbit", "loss": "3%"}, "desc": "LPWAN"},
    "12": {"name": "12", "params": {"delay": "150ms", "jitter": "80ms", "loss": "10%", "corrupt": "2%"}, "desc": "Zone catastrophe"},
    "13": {"name": "13", "params": {"delay": "150ms", "jitter": "2ms", "rate": "1000mbit", "loss": "0.01%"}, "desc": "Latence fixe physique"},
    "14": {"name": "14", "params": {"delay": "40ms", "jitter": "50ms", "rate": "50mbit", "loss": "3%", "corrupt": "1%"}, "desc": "Mobilité extrême (Jitter)"}
}

class NetworkManager:
    @staticmethod
    def run(cmd: str):
        try:
            subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            print(f"TC Error: {e.stderr.decode().strip()}")

    @classmethod
    def flash_reset(cls):
        print(f"\n[!] FLASHING INTERFACE {INTERFACE}: Removing all emulation...")
        cls.run(f"sudo tc qdisc del dev {INTERFACE} root 2>/dev/null || true")

    @classmethod
    def apply(cls, config: Dict):
        cls.flash_reset()
        base_cmd = f"sudo tc qdisc add dev {INTERFACE} root netem"
        parts = []
        if "delay" in config:
            d_str = f"delay {config['delay']}"
            if "jitter" in config: d_str += f" {config['jitter']}"
            parts.append(d_str)
        if "loss" in config: parts.append(f"loss {config['loss']}")
        if "rate" in config: parts.append(f"rate {config['rate']}")
        if "corrupt" in config: parts.append(f"corrupt {config['corrupt']}")
        
        full_cmd = f"{base_cmd} {' '.join(parts)}"
        print(f"\n[+] Applied Network Rules: {full_cmd}")
        cls.run(full_cmd)

class DittoProducer:
    def __init__(self, json_path, freq):
        self.json_path = json_path
        self.last_sim_time = -1.0
        self.interval = 1.0 / freq
        self.packet_id_counter = 0
        
        # Initialisation du log des IDs
        try:
            with open(IDS_LOG_PATH, "w") as f:
                f.write("PacketID\tTimestampMS\tReadableTime\n")
        except Exception as e:
            print(f"[ERROR] Could not initialize ID log file: {e}")

    def _clean_name(self, name):
        return name.replace("[", "").replace("]", "")

    def _log_sent_id(self, packet_id):
        ts_ms = int(time.time() * 1000)
        ts_readable = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with open(IDS_LOG_PATH, "a") as f:
            f.write(f"{packet_id}\t{ts_ms}\t{ts_readable}\n")

    def _update_node_in_ditto(self, node):
        node_id = node['id']
        thing_id = f"{DITTO_NAMESPACE}:{node_id}"
        
        # Payload simplifié : tout est mis à plat dans attributes
        payload = {
            "attributes": node
        }
        self._send_patch(thing_id, payload)

    def _update_flow_in_ditto(self, flow):
        src = self._clean_name(flow['src'])
        dst = self._clean_name(flow['dst'])
        thing_id = f"{DITTO_NAMESPACE}:{src}_to_{dst}"
        
        # Payload simplifié : tout est mis à plat dans attributes
        payload = {
            "attributes": flow
        }
        self._send_patch(thing_id, payload)

    def _send_patch(self, thing_id, payload):
        url = f"{DITTO_URL}/api/2/things/{thing_id}"
        headers = {"Content-Type": "application/merge-patch+json"}
        try:
            r = requests.patch(
                url,
                auth=(DITTO_USER, DITTO_PASSWORD),
                headers=headers,
                data=json.dumps(payload),
                timeout=2
            )
            if r.status_code in [200, 204]:
                pass
            else:
                print(f"[DITTO] Warning {thing_id}: {r.status_code}")
        except Exception as e:
            print(f"[DITTO ERROR] {thing_id} failed: {e}")

    def run_forever(self):
        print(f"[*] Starting JSON Sync at {GLOBAL_FREQ} Hz...")
        
        while True:
            start_time = time.time()
            try:
                if os.path.exists(self.json_path):
                    with open(self.json_path, "r") as f:
                        content = f.read().strip()
                        if content:
                            if not content.endswith("]"): content += "]"
                            
                            data = json.loads(content)
                            if data:
                                last_snapshot = data[-1]
                                sim_time = last_snapshot["timestamp"]

                                if sim_time > self.last_sim_time:
                                    self.last_sim_time = sim_time
                                    
                                    # Update Nodes
                                    for node in last_snapshot.get("nodes", []):
                                        self.packet_id_counter += 1
                                        self._update_node_in_ditto(node)
                                        self._log_sent_id(self.packet_id_counter)
                                    
                                    # Update Flows
                                    for flow in last_snapshot.get("flows", []):
                                        self._update_flow_in_ditto(flow)
                                    
                                    print(f"[SYNC] SimTime: {sim_time}s | Nodes: {len(last_snapshot.get('nodes',[]))}")

            except (json.JSONDecodeError, Exception) as e:
                pass

            elapsed = time.time() - start_time
            time.sleep(max(0, self.interval - elapsed))

def main():
    if os.geteuid() != 0:
        print("CRITICAL: Run with 'sudo' for tc rules.")
        sys.exit(1)

    nm = NetworkManager()
    
    print("\n" + "=" * 60)
    print(" DIGITAL TWIN SYNC TOOL (JSON MODE)")
    print(f" Frequency: {GLOBAL_FREQ} Hz | Namespace: {DITTO_NAMESPACE}")
    print("=" * 60)

    print("\n[1] Select Network Profile:")
    for k, v in NETWORK_PROFILES.items():
        print(f"   {k}. {v['name']} --> {v['desc']}")
    
    choice = input("\nChoice (C=Custom, N=None, F=Flash): ").upper()

    config_to_apply = {}
    if choice == 'F': nm.flash_reset(); return
    elif choice == 'N': nm.flash_reset()
    elif choice in NETWORK_PROFILES: config_to_apply = NETWORK_PROFILES[choice]["params"]

    if config_to_apply:
        nm.apply(config_to_apply)

    producer = DittoProducer(JSON_FILE_PATH, GLOBAL_FREQ)
    
    try:
        producer.run_forever()
    except KeyboardInterrupt:
        print("\n[!] Stopping...")
    finally:
        nm.flash_reset()

if __name__ == "__main__":
    main()