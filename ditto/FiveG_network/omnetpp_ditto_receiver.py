

# # import socket
# # import json
# # import requests
# # import os
# # import time
# # import sys

# # # --- CONFIGURATION ---
# # UDP_IP = "10.255.0.1" 
# # UDP_PORT = 9999
# # DITTO_URL = "http://127.0.0.1:8080/api/2/things"
# # AUTH = ("ditto", "ditto")
# # NS = "my5GNetwork"

# # SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# # RECV_LOG_PATH = os.path.join(SCRIPT_DIR, "received_packet_ids.txt")

# # session = requests.Session()
# # session.auth = AUTH

# # def clean_id(val):
# #     return str(val).replace("[", "").replace("]", "")

# # def update_ditto(thing_id, attributes):
# #     url = f"{DITTO_URL}/{thing_id}"
# #     headers = {'Content-Type': 'application/merge-patch+json'}
# #     payload = {"attributes": attributes}
# #     try:
# #         res = session.patch(url, json=payload, headers=headers, timeout=0.5)
# #         return res.status_code
# #     except:
# #         return 500

# # def main():
# #     with open(RECV_LOG_PATH, "w") as f:
# #         f.write("SnapshotID\tTimestampMS\tSimTime\tStatus\n")

# #     sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# #     sock.bind((UDP_IP, UDP_PORT))
# #     # TIMEOUT : si on ne reçoit rien pendant 200 secondes, on lève une exception
# #     sock.settimeout(200.0) 

# #     print(f"[*] Receiver prêt sur {UDP_IP}:{UDP_PORT}")
# #     print(f"[*] Appuyez sur Ctrl+C ou coupez l'émetteur pour arrêter.")

# #     try:
# #         while True:
# #             try:
# #                 data, addr = sock.recvfrom(65535)
# #                 recv_ts_ms = int(time.time() * 1000)
                
# #                 packet = json.loads(data.decode())
                
# #                 # --- CORRECTION DES CLÉS ---
# #                 sim_time = packet.get("t", 0) # 't' au lieu de 'sim_time'
# #                 nodes = packet.get("n", [])   # 'n' au lieu de 'nodes'
# #                 flows = packet.get("f", [])   # 'f' au lieu de 'flows'
                
# #                 print(f"\n[RX] Temps Simu: {sim_time} reçu. Mise à jour Ditto...")
                
# #                 success = True
                
# #                 # Mise à jour des Nodes
# #                 for node in nodes:
# #                     t_id = f"{NS}:{clean_id(node['id'])}"
# #                     # On envoie x, y, z à Ditto
# #                     status = update_ditto(t_id, {"x": node['x'], "y": node['y'], "z": node['z']})
# #                     if status != 204: success = False

# #                 # Mise à jour des Flows
# #                 for flow in flows:
# #                     # 's' = src, 'd' = dst
# #                     t_id = f"{NS}:{clean_id(flow['s'])}_to_{clean_id(flow['d'])}"
# #                     # 'sz' = packet_size, 'i' = interval
# #                     attrs = {
# #                         "packet_size": flow['sz'],
# #                         "interval": flow['i']
# #                     }
# #                     status = update_ditto(t_id, attrs)
# #                     if status != 204: success = False

# #                 if success:
# #                     print(f" [OK] Synchronisation Ditto réussie.")
# #                 else:
# #                     print(f" [FAIL] Erreur lors de la mise à jour Ditto.")

# #             except socket.timeout:
# #                 print("\n[!] Timeout...")
# #                 break

# #             except socket.timeout:
# #                 # Si l'émetteur s'arrête, on tombe ici toutes les 2 secondes
# #                 # On peut choisir de continuer à attendre ou de quitter.
# #                 # Pour votre besoin : on quitte si l'émetteur ne parle plus.
# #                 print("\n[!] Aucune donnée reçue (Émetteur coupé ?). Arrêt du récepteur...")
# #                 break 

# #     except KeyboardInterrupt:
# #         print("\n[Terminé] Arrêt manuel par l'utilisateur.")
# #     finally:
# #         sock.close()

# # if __name__ == "__main__":
# #     main()


# import socket
# import json
# import requests
# import time
# import threading
# from scapy.all import Ether, IP, UDP, Raw, sendp

# # --- CONFIGURATION RÉSEAU ---
# UDP_RECV_IP = "10.255.0.1" 
# UDP_RECV_PORT = 9999

# NS3_TAP_INTERFACE = "thetap"
# NS3_IP = "10.1.1.2"
# NS3_MAC = "00:00:00:00:00:02"
# NS3_PORT = 5000

# # --- CONFIGURATION DITTO ---
# DITTO_URL = "http://127.0.0.1:8080/api/2/things"
# AUTH = ("ditto", "ditto")
# NS = "my5GNetwork"

# session = requests.Session()
# session.auth = AUTH

# def log(msg):
#     print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

# def forward_to_ns3(raw_data):
#     """Envoi immédiat à ns-3 sans attendre Ditto."""
#     try:
#         pkt = (Ether(dst=NS3_MAC) /
#                IP(dst=NS3_IP) /
#                UDP(sport=54321, dport=NS3_PORT) /
#                Raw(load=raw_data))
#         sendp(pkt, iface=NS3_TAP_INTERFACE, verbose=False)
#     except Exception as e:
#         log(f"Erreur Scapy : {e}")

# def ditto_patch_worker(thing_id, attributes):
#     """Effectue la requête HTTP PATCH en tâche de fond."""
#     url = f"{DITTO_URL}/{thing_id}"
#     headers = {'Content-Type': 'application/merge-patch+json'}
#     payload = {"attributes": attributes}
#     try:
#         session.patch(url, json=payload, headers=headers, timeout=0.5)
#     except:
#         pass

# def main():
#     # Socket pour recevoir d'OMNeT++
#     sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#     sock.bind((UDP_RECV_IP, UDP_RECV_PORT))

#     log("=== SUPER-PONT DITTO-NS3 ACTIF ===")
    
#     try:
#         while True:
#             # 1. On reçoit le paquet d'OMNeT++
#             data, addr = sock.recvfrom(65535)
            
#             # 2. PRIORITÉ : On l'envoie à ns-3 TOUT DE SUITE
#             forward_to_ns3(data)
            
#             # 3. ON ANALYSE POUR DITTO (En parallèle)
#             packet = json.loads(data.decode())
#             current_t = packet.get("t")
            
#             # Mise à jour des Nodes (UEs)
#             for node in packet.get("n", []):
#                 t_id = f"{NS}:{node['id']}".replace("[", "").replace("]", "")
#                 attrs = {"x": node['x'], "y": node['y'], "z": node['z']}
#                 # On lance un Thread pour ne pas bloquer la réception UDP
#                 threading.Thread(target=ditto_patch_worker, args=(t_id, attrs)).start()

#             # Mise à jour des Flux
#             for flow in packet.get("f", []):
#                 t_id = f"{NS}:{flow['s']}_to_{flow['d']}".replace("[", "").replace("]", "")
#                 attrs = {"packet_size": flow['sz'], "interval": flow['i']}
#                 threading.Thread(target=ditto_patch_worker, args=(t_id, attrs)).start()

#             log(f"Snapshot t={current_t} transféré à ns-3 et envoyé à Ditto.")

#     except KeyboardInterrupt:
#         log("Arrêt du pont.")
#     finally:
#         sock.close()

# if __name__ == "__main__":
#     main()  



import socket
import json
import requests
import time
import threading
import os
import signal
import sys
from scapy.all import Ether, IP, UDP, Raw, sendp

# --- CONFIGURATION ---
UDP_RECV_IP = "10.255.0.1" 
UDP_RECV_PORT = 9999
NS3_TAP_INTERFACE = "thetap"
NS3_IP = "10.1.1.2"
NS3_MAC = "00:00:00:00:00:02"
NS3_PORT = 5000
DITTO_URL = "http://127.0.0.1:8080/api/2/things"
AUTH = ("ditto", "ditto")
NS = "my5GNetwork"

# Fichiers de sortie
LAST_STATE_FILE = "last_ditto_state.json" # 
FULL_DATASET_FILE = "sync_dataset.json"   # 

session = requests.Session()
session.auth = AUTH
sync_history = []

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def forward_to_ns3(raw_data):
    try:
        pkt = (Ether(dst=NS3_MAC) / IP(dst=NS3_IP) / UDP(sport=54321, dport=NS3_PORT) / Raw(load=raw_data))
        sendp(pkt, iface=NS3_TAP_INTERFACE, verbose=False)
    except: pass

def ditto_patch_worker(thing_id, attributes):
    url = f"{DITTO_URL}/{thing_id}"
    headers = {'Content-Type': 'application/merge-patch+json'}
    payload = {"attributes": attributes}
    try:
        session.patch(url, json=payload, headers=headers, timeout=0.5)
    except: pass

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_RECV_IP, UDP_RECV_PORT))
    log(f"=== PONT ACTIF : UDP -> DITTO & NS-3 ===")

    try:
        while True:
            data, addr = sock.recvfrom(65535)
            arrival_real_time = time.time()
            
            # 1. Envoi ns-3
            forward_to_ns3(data)
            
            # 2. Parsing
            try:
                packet = json.loads(data.decode())
                sim_time = packet.get("t")
                
                # 3. Sauvegarde immédiate pour le Watcher (FICHE LIVE)
                live_snapshot = {
                    "sim_time": sim_time,
                    "arrival_time": arrival_real_time,
                    "nodes": packet.get("n", []),
                    "flows": packet.get("f", [])
                }
                with open(LAST_STATE_FILE, 'w') as f:
                    json.dump(live_snapshot, f)

                # 4. Envoi Ditto (Threads pour ne pas bloquer)
                for node in packet.get("n", []):
                    t_id = f"{NS}:{node['id']}".replace("[", "").replace("]", "")
                    attrs = {"x": node['x'], "y": node['y'], "z": node.get("z", 1.5)}
                    threading.Thread(target=ditto_patch_worker, args=(t_id, attrs)).start()

                # Optionnel : garder en mémoire pour le log final
                sync_history.append(live_snapshot)
                
                if len(sync_history) % 20 == 0:
                    log(f"Snapshot sim_t={sim_time} traité et partagé.")

            except Exception as e:
                log(f"Erreur data: {e}")

    except KeyboardInterrupt:
        log("Arrêt...")
        with open(FULL_DATASET_FILE, 'w') as f:
            json.dump(sync_history, f)
    finally:
        sock.close()

if __name__ == "__main__":
    main()