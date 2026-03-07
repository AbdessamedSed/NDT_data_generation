import subprocess
import os
import sys
import time
import requests
from typing import Dict
import json
from datetime import datetime

GLOBAL_FREQ = 10  
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE_PATH = os.path.join(SCRIPT_DIR, "..", "simulations", "network_state.json")
IDS_LOG_PATH = os.path.join(SCRIPT_DIR, "..", "simulations", "sent_packet_ids.txt")
CONFIG_EXPORT_PATH = os.path.join(SCRIPT_DIR, "current_network_config.json")

INTERFACE = "lo"
DITTO_URL = "http://localhost:8080"
DITTO_USER = "ditto"
DITTO_PASSWORD = "ditto"
DITTO_NAMESPACE = "my5GNetwork"

NETWORK_PROFILES = {
    "1": {"name": "1", "params": {"delay": "1ms", "jitter": "0.1ms", "rate": "1000mbit", "loss": "0%"}, "desc": "Filaire ultra-stable"},
    "3": {"name": "3", "params": {"delay": "10ms", "jitter": "1ms", "rate": "500mbit", "loss": "0.01%"}, "desc": "5G Charge moyenne"},
    "12": {"name": "12", "params": {"delay": "150ms", "jitter": "80ms", "loss": "10%", "corrupt": "2%"}, "desc": "Zone catastrophe"}
}

def save_network_config(freq, profile_data):
    config_data = {"sending_frequency_hz": freq, "network_parameters": profile_data.get("params", {})}
    try:
        with open(CONFIG_EXPORT_PATH, "w") as f:
            json.dump(config_data, f, indent=4)
        print(f"\n[CONFIG] Paramètres sauvegardés dans {CONFIG_EXPORT_PATH}")
    except Exception as e:
        print(f"[ERREUR CONFIG] Impossible de sauvegarder : {e}")

class NetworkManager:
    @staticmethod
    def run(cmd: str):
        try:
            subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            print(f"TC Error: {e.stderr.decode().strip()}")

    @classmethod
    def flash_reset(cls):
        cls.run(f"sudo tc qdisc del dev {INTERFACE} root 2>/dev/null || true")

    @classmethod
    def apply(cls, config: Dict):
        cls.flash_reset()
        base_cmd = f"sudo tc qdisc add dev {INTERFACE} root netem"
        parts = [f"delay {config['delay']} {config.get('jitter','')}".strip()] if "delay" in config else []
        if "loss" in config: parts.append(f"loss {config['loss']}")
        if "rate" in config: parts.append(f"rate {config['rate']}")
        full_cmd = f"{base_cmd} {' '.join(parts)}"
        print(f"[+] Réseau configuré : {full_cmd}")
        cls.run(full_cmd)

class DittoProducer:
    def __init__(self, json_path, freq):
        self.json_path = json_path
        self.last_sim_time = -1.0
        self.interval = 1.0 / freq
        self.packet_id_counter = 0
        
        # Initialisation du log TXT
        with open(IDS_LOG_PATH, "w") as f:
            f.write("PacketID\tTimestampMS\tStatus\n")

    def _log_sent_id(self, packet_id, status):
        ts_ms = int(time.time() * 1000)
        with open(IDS_LOG_PATH, "a") as f:
            f.write(f"{packet_id}\t{ts_ms}\t{status}\n")

    def _send_patch(self, thing_id, payload, packet_id):
        url = f"{DITTO_URL}/api/2/things/{thing_id}"
        headers = {"Content-Type": "application/merge-patch+json"}
        
        try:
            r = requests.patch(url, auth=(DITTO_USER, DITTO_PASSWORD), headers=headers, data=json.dumps(payload), timeout=1)
            
            if r.status_code in [200, 204]:
                print(f"  [OK] ID:{packet_id} -> {thing_id} (HTTP {r.status_code})")
                self._log_sent_id(packet_id, "SUCCESS")
            else:
                print(f"  [!!] ERREUR ID:{packet_id} -> {thing_id} (Code: {r.status_code})")
                print(f"       Détail: {r.text}")
                self._log_sent_id(packet_id, f"HTTP_ERR_{r.status_code}")
        
        except requests.exceptions.ConnectionError:
            print(f"  [FATAL] Impossible de joindre Ditto sur {DITTO_URL} !")
            self._log_sent_id(packet_id, "CONN_ERROR")
        except Exception as e:
            print(f"  [EXCEPT] ID:{packet_id} : {str(e)}")
            self._log_sent_id(packet_id, "EXCEPTION")

    def sync_update(self, node_or_flow, is_node=True):
        self.packet_id_counter += 1
        p_id = self.packet_id_counter
        
        if is_node:
            thing_id = f"{DITTO_NAMESPACE}:{node_or_flow['id']}"
            payload = {
                "attributes": {
                    "info": {"id": node_or_flow['id'], "packet_id": p_id},
                    "mobility": {"pos": {"x": node_or_flow['x'], "y": node_or_flow['y']}}
                }
            }
        else:
            src = node_or_flow['src'].replace("[","").replace("]","")
            dst = node_or_flow['dst'].replace("[","").replace("]","")
            thing_id = f"{DITTO_NAMESPACE}:{src}_to_{dst}"
            payload = {"attributes": {"parameters": {"packet_id": p_id, "throughput": node_or_flow['throughput']}}}
        
        self._send_patch(thing_id, payload, p_id)

    def run_forever(self):
        print(f"[*] Monitoring de {self.json_path} à {GLOBAL_FREQ}Hz...")
        while True:
            start_loop = time.time()
            try:
                if os.path.exists(self.json_path):
                    with open(self.json_path, "r") as f:
                        data = json.loads(f.read())
                        if data:
                            last = data[-1]
                            if last["timestamp"] > self.last_sim_time:
                                self.last_sim_time = last["timestamp"]
                                print(f"\n--- Snapshot SimTime: {self.last_sim_time}s ---")
                                
                                for n in last.get("nodes", []): self.sync_update(n, True)
                                for f in last.get("flows", []): self.sync_update(f, False)
            except Exception as e:
                pass # Erreur de lecture JSON (souvent quand OMNeT++ écrit en même temps)

            time.sleep(max(0, self.interval - (time.time() - start_loop)))

def main():
    if os.getuid() != 0:
        print("Lancer avec 'sudo'"); sys.exit(1)

    nm = NetworkManager()
    print("\n" + "="*40 + "\n SYNC TOOL : MODE VERBEUX\n" + "="*40)
    
    for k, v in NETWORK_PROFILES.items(): print(f" {k}. {v['desc']}")
    choice = input("\nChoix : ").upper()

    if choice in NETWORK_PROFILES:
        save_network_config(GLOBAL_FREQ, NETWORK_PROFILES[choice])
        nm.apply(NETWORK_PROFILES[choice]["params"])
        
        producer = DittoProducer(JSON_FILE_PATH, GLOBAL_FREQ)
        try:
            producer.run_forever()
        except KeyboardInterrupt:
            print("\nArrêt...")
        finally:
            nm.flash_reset()

if __name__ == "__main__":
    main()