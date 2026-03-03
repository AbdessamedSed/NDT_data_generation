# from scapy.all import *
# import json
# import requests
# import time
# import os
# import hashlib

# # ===============================
# # CONFIGURATION
# # ===============================
# interface = "thetap"
# target_ip = "10.1.1.2"
# target_mac = "00:00:00:00:00:02" # MAC ns-3 (Node 1)
# target_port = 5000

# src_ip = "10.1.1.10"
# src_mac = "06:53:88:13:15:81" # Ta MAC Linux (ip link show thetap)

# DITTO_URL = "http://localhost:8080/api/2/things"
# RAM_BUFFER_PATH = "/dev/shm/ditto_buffer.json"

# # Variable pour stocker l'état précédent
# last_payload_hash = None

# def send_update_signal():
#     """ Envoie un minuscule paquet UDP pour réveiller ns-3 """
#     packet = (
#         Ether(src=src_mac, dst=target_mac) /
#         IP(src=src_ip, dst=target_ip) /
#         UDP(sport=54321, dport=target_port) /
#         Raw(load="UPDATE")
#     )
#     sendp(packet, iface=interface, verbose=False)

# print(f"=== Optimized RAM Sync starting on {interface} ===")

# while True:
#     try:
#         # 1. Récupérer les données de Ditto
#         r = requests.get(DITTO_URL, auth=('ditto','ditto'), timeout=2)
        
#         if r.status_code == 200:
#             data = r.json()
            
#             # 2. Comparaison : On crée une chaîne triée pour comparer le contenu
#             # On trie les clés pour être sûr que l'ordre ne change pas le résultat
#             current_payload_str = json.dumps(data, sort_keys=True)
#             current_hash = hashlib.md5(current_payload_str.encode()).hexdigest()

#             if current_hash != last_payload_hash:
#                 # 3. Les données ont changé !
#                 print(f"[{time.strftime('%H:%M:%S')}] 🆕 Changement détecté dans Ditto.")
                
#                 # Écrire le JSON complet dans la RAM (/dev/shm)
#                 with open(RAM_BUFFER_PATH, "w") as f:
#                     f.write(current_payload_str)
                
#                 # Envoyer l'alerte UDP via Scapy
#                 send_update_signal()
                
#                 # Mettre à jour l'ancien hash
#                 last_payload_hash = current_hash
#             else:
#                 # Aucune modification
#                 pass 
            
#         time.sleep(0.05) # On peut vérifier Ditto toutes les 50ms sans problème

#     except Exception as e:
#         print(f"Erreur : {e}")
#         time.sleep(2)


from scapy.all import *
import json
import requests
import time
import os

# ===============================
# CONFIGURATION
# ===============================
interface = "thetap"
target_ip = "10.1.1.2"
target_mac = "00:00:00:00:00:02" # MAC ns-3
target_port = 5000

# IPs Scapy (pour tricher l'ARP)
src_ip = "10.1.1.10"
src_mac = "06:53:88:13:15:81" # Ta MAC Linux

DITTO_URL = "http://localhost:8080/api/2/things"
RAM_BUFFER_PATH = "/dev/shm/ditto_buffer.json"

def send_update_signal():
    # On crée un tout petit paquet UDP de "réveil"
    # Comme il est minuscule, aucun problème de MTU
    packet = (
        Ether(src=src_mac, dst=target_mac) /
        IP(src=src_ip, dst=target_ip) /
        UDP(sport=54321, dport=target_port) /
        Raw(load="UPDATE")
    )
    sendp(packet, iface=interface, verbose=False)

print(f"=== RAM BUFFER SYNC STARTING ON {interface} ===")

while True:
    try:
        # 1. Récupérer les données de Ditto
        r = requests.get(DITTO_URL, auth=('ditto','ditto'), timeout=2)
        
        if r.status_code == 200:
            data = r.json()
            
            # 2. Écrire le JSON dans la RAM (/dev/shm)
            # C'est extrêmement rapide
            with open(RAM_BUFFER_PATH, "w") as f:
                json.dump(data, f)
            
            # 3. Envoyer l'alerte à ns-3 via Scapy
            send_update_signal()
            
            print(f"[{time.strftime('%H:%M:%S')}] Signal d'alerte envoyé (JSON mis en RAM)")
            
        time.sleep(1) # Fréquence de 2Hz (ajustable)

    except Exception as e:
        print(f"Erreur : {e}")
        time.sleep(2)