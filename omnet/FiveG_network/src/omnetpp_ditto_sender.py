import socket
import json
import os
import time
import subprocess
import sys
from datetime import datetime

# --- CONFIGURATION ---
GLOBAL_FREQ = 10  # This ensures 10 packets per second (0.1s interval)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(SCRIPT_DIR, "..", "simulations", "network_state.json")
IDS_LOG_PATH = os.path.join(SCRIPT_DIR, "..", "simulations", "sent_packet_ids.txt")

UDP_IP = "127.0.0.1"
UDP_PORT = 9999
INTERFACE = "lo"

NETWORK_PROFILES = {
    "1": {"delay": "1ms", "loss": "0%", "rate": "1000mbit", "desc": "Ideal Link"},
    "2": {"delay": "10ms", "loss": "2%", "rate": "100mbit", "loss": "10%", "desc": "Standard 5G"},
    "3": {"delay": "200ms", "loss": "15%", "rate": "1mbit", "desc": "Congested Link"}
}

def apply_network_conditions(config):
    subprocess.run(f"sudo tc qdisc del dev {INTERFACE} root 2>/dev/null || true", shell=True)
    cmd = f"sudo tc qdisc add dev {INTERFACE} root netem delay {config['delay']} loss {config['loss']} rate {config['rate']}"
    subprocess.run(cmd, shell=True)
    print(f"\n[TC] Applied: {config['desc']} (Delay: {config['delay']}, Loss: {config['loss']})")

def main():
    if os.getuid() != 0:
        print("CRITICAL: Run with 'sudo' for tc commands."); sys.exit(1)

    # 1. Initialize Log File with Headers
    with open(IDS_LOG_PATH, "w") as f:
        f.write("SnapshotID\tTimestampMS\tSimTimeInPacket\tStatus\n")

    print("\n" + "="*50 + "\n  EDGE SENDER: STRICT 10Hz MODE\n" + "="*50)
    for k, v in NETWORK_PROFILES.items(): print(f" {k}. {v['desc']}")
    
    choice = input("\nSelect Profile: ")
    if choice in NETWORK_PROFILES:
        apply_network_conditions(NETWORK_PROFILES[choice])
    else:
        print("Invalid choice. Exiting."); return

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    snapshot_id = 0

    print(f"[*] Logging to: {IDS_LOG_PATH}")
    print(f"[*] Frequency: {GLOBAL_FREQ}Hz (1 packet every {1.0/GLOBAL_FREQ}s)")

    while True:
        start_time = time.time() # Start clock for frequency control
        
        try:
            if os.path.exists(JSON_PATH):
                with open(JSON_PATH, "r") as f:
                    content = f.read().strip()
                    if content:
                        # Fix JSON if OMNeT++ is currently writing to it
                        if not content.endswith("]"): content += "]"
                        data = json.loads(content)
                        
                        if data:
                            # ALWAYS TAKE THE LAST VALUE FOUND
                            last_snapshot = data[-1]
                            sim_time_val = last_snapshot.get("timestamp", 0)
                            
                            snapshot_id += 1
                            
                            # CREATE THE SINGLE AGGREGATED PACKET
                            packet = {
                                "snapshot_id": snapshot_id,
                                "sim_time": sim_time_val,
                                "nodes": last_snapshot.get("nodes", []),
                                "flows": last_snapshot.get("flows", [])
                            }
                            
                            # SEND VIA UDP (Subject to TC conditions)
                            message = json.dumps(packet).encode()
                            sock.sendto(message, (UDP_IP, UDP_PORT))
                            
                            # LOG PACKET ID TO TXT (As requested)
                            ts_ms = int(time.time() * 1000)
                            with open(IDS_LOG_PATH, "a") as log_f:
                                log_f.write(f"{snapshot_id}\t{ts_ms}\t{sim_time_val}\tSENT\n")
                            
                            print(f" [TX] Packet #{snapshot_id} | Data SimTime: {sim_time_val}s | Size: {len(message)} bytes")

        except Exception as e:
            # If JSON is being updated by OMNeT++, we might get a read error
            # We just skip that specific millisecond and continue
            pass

        # CONTROL FREQUENCY: Calculate how much time to sleep to stay at 10Hz
        elapsed = time.time() - start_time
        sleep_time = (1.0 / GLOBAL_FREQ) - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

if __name__ == "__main__":
    main()

# import subprocess
# import os
# import sys
# import time
# import requests
# from typing import Dict
# import json

# # --- CONFIGURATION ---
# GLOBAL_FREQ = 10  
# SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# JSON_FILE_PATH = os.path.join(SCRIPT_DIR, "..", "simulations", "network_state.json")
# IDS_LOG_PATH = os.path.join(SCRIPT_DIR, "..", "simulations", "sent_packet_ids.txt")
# CONFIG_EXPORT_PATH = os.path.join(SCRIPT_DIR, "current_network_config.json")

# INTERFACE = "lo"
# DITTO_BATCH_URL = "http://localhost:8080/api/2/batch"
# DITTO_USER = "ditto"
# DITTO_PASSWORD = "ditto"
# NS = "my5GNetwork"

# NETWORK_PROFILES = {
#     "1": {"name": "1", "params": {"delay": "1ms", "jitter": "0.1ms", "rate": "1000mbit", "loss": "0%"}, "desc": "Filaire ultra-stable"},
#     "3": {"name": "3", "params": {"delay": "10ms", "jitter": "1ms", "rate": "500mbit", "loss": "0.01%"}, "desc": "5G Charge moyenne"},
#     "12": {"name": "12", "params": {"delay": "150ms", "jitter": "80ms", "loss": "10%", "corrupt": "2%"}, "desc": "Zone catastrophe"}
# }

# def save_network_config(freq, profile_data):
#     """Exporte les paramètres réseau en JSON local."""
#     config_data = {"sending_frequency_hz": freq, "network_parameters": profile_data.get("params", {})}
#     try:
#         with open(CONFIG_EXPORT_PATH, "w") as f:
#             json.dump(config_data, f, indent=4)
#         print(f"[EXPORT] Config sauvegardée dans {CONFIG_EXPORT_PATH}")
#     except Exception as e:
#         print(f"[ERROR] Export config: {e}")

# class NetworkManager:
#     @staticmethod
#     def run(cmd: str):
#         try:
#             subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
#         except subprocess.CalledProcessError as e:
#             print(f"TC Error: {e.stderr.decode().strip()}")

#     @classmethod
#     def flash_reset(cls):
#         cls.run(f"sudo tc qdisc del dev {INTERFACE} root 2>/dev/null || true")

#     @classmethod
#     def apply(cls, config: Dict):
#         cls.flash_reset()
#         base_cmd = f"sudo tc qdisc add dev {INTERFACE} root netem"
#         parts = [f"delay {config['delay']} {config.get('jitter','')}".strip()] if "delay" in config else []
#         if "loss" in config: parts.append(f"loss {config['loss']}")
#         if "rate" in config: parts.append(f"rate {config['rate']}")
#         full_cmd = f"{base_cmd} {' '.join(parts)}"
#         print(f"[+] TC Rules: {full_cmd}")
#         cls.run(full_cmd)

# class DittoBatchProducer:
#     def __init__(self, json_path, freq):
#         self.json_path = json_path
#         self.last_sim_time = -1.0
#         self.interval = 1.0 / freq
#         self.snapshot_id_counter = 0
#         with open(IDS_LOG_PATH, "w") as f:
#             f.write("SnapshotID\tTimestampMS\tSimTime\tStatus\n")

#     def _clean(self, val):
#         return str(val).replace("[", "").replace("]", "")

#     def _send_batch(self, commands, snapshot_id, sim_time):
#         """Envoie une liste d'instructions à Ditto en UNE SEULE requête HTTP POST."""
#         auth = (DITTO_USER, DITTO_PASSWORD)
#         headers = {"Content-Type": "application/json"}
        
#         try:
#             # On envoie toutes les commandes d'un coup
#             r = requests.post(DITTO_BATCH_URL, auth=auth, headers=headers, data=json.dumps(commands), timeout=2)
            
#             status = "OK" if r.status_code in [200, 202] else f"ERR_{r.status_code}"
#             print(f" [BATCH TX] Snapshot #{snapshot_id} | SimTime: {sim_time}s | HTTP: {status} ({len(commands)} items)")
            
#             # Log TXT
#             ts_ms = int(time.time() * 1000)
#             with open(IDS_LOG_PATH, "a") as f:
#                 f.write(f"{snapshot_id}\t{ts_ms}\t{sim_time}\t{status}\n")
            
#             if r.status_code >= 400:
#                 print(f"      Détail erreur: {r.text}")
#         except Exception as e:
#             print(f" [!!] Snapshot #{snapshot_id} | Erreur Connexion: {e}")

#     def run_forever(self):
#         print(f"[*] Passerelle Batch démarrée ({GLOBAL_FREQ}Hz)...")
#         while True:
#             start_loop = time.time()
#             try:
#                 if os.path.exists(self.json_path):
#                     with open(self.json_path, "r") as f:
#                         content = f.read().strip()
#                         if content:
#                             if not content.endswith("]"): content += "]"
#                             data = json.loads(content)
#                             if data:
#                                 last = data[-1]
#                                 if last["timestamp"] > self.last_sim_time:
#                                     self.last_sim_time = last["timestamp"]
#                                     self.snapshot_id_counter += 1
                                    
#                                     # Préparation du BATCH (Liste de commandes)
#                                     batch_commands = []
                                    
#                                     # Commandes pour les Nodes
#                                     for node in last.get("nodes", []):
#                                         t_id = f"{NS}:{self._clean(node['id'])}"
#                                         batch_commands.append({
#                                             "op": "modify",
#                                             "path": f"/things/{t_id}/attributes",
#                                             "value": {k: v for k, v in node.items() if k != 'id'}
#                                         })
                                    
#                                     # Commandes pour les Flows
#                                     for flow in last.get("flows", []):
#                                         src, dst = self._clean(flow['src']), self._clean(flow['dst'])
#                                         t_id = f"{NS}:{src}_to_{dst}"
#                                         batch_commands.append({
#                                             "op": "modify",
#                                             "path": f"/things/{t_id}/attributes",
#                                             "value": flow
#                                         })
                                    
#                                     # ENVOI UNIQUE
#                                     if batch_commands:
#                                         self._send_snapshot(batch_commands, self.snapshot_id_counter, self.last_sim_time)
#             except Exception: pass
#             time.sleep(max(0, self.interval - (time.time() - start_loop)))

#     # Alias pour la fonction d'envoi
#     def _send_snapshot(self, cmds, sid, stime):
#         self._send_batch(cmds, sid, stime)

# def main():
#     if os.getuid() != 0:
#         print("Lancer avec sudo."); sys.exit(1)

#     nm = NetworkManager()
#     print("\n" + "="*50 + "\n  THESIS SYNC: BATCH API MODE (SINGLE REQUEST)\n" + "="*50)
    
#     for k, v in NETWORK_PROFILES.items(): print(f" {k}. {v['desc']}")
#     choice = input("\nChoix : ").upper()
    
#     if choice in NETWORK_PROFILES:
#         save_network_config(GLOBAL_FREQ, NETWORK_PROFILES[choice])
#         nm.apply(NETWORK_PROFILES[choice]["params"])
        
#         producer = DittoBatchProducer(JSON_FILE_PATH, GLOBAL_FREQ)
#         try:
#             producer.run_forever()
#         except KeyboardInterrupt: print("\nArrêt.")
#         finally: nm.flash_reset()

# if __name__ == "__main__":
#     main()