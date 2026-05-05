# from scapy.all import *
# import json
# import requests
# import time
# import os

# # ===============================
# # CONFIGURATION
# # ===============================
# interface = "thetap"
# target_ip = "10.1.1.2"
# target_mac = "00:00:00:00:00:02" # MAC ns-3 
# target_port = 5000

# # IPs Scapy 
# src_ip = "10.1.1.10"
# src_mac = "06:53:88:13:15:81" # Ta MAC Linux

# DITTO_URL = "http://localhost:8080/api/2/things"
# RAM_BUFFER_PATH = "/dev/shm/ditto_buffer.json"

# def send_update_signal():
#     # On crée un tout petit paquet UDP de "réveil"
#     # Comme il est minuscule, aucun problème de MTU
#     packet = (
#         Ether(src=src_mac, dst=target_mac) /
#         IP(src=src_ip, dst=target_ip) /
#         UDP(sport=54321, dport=target_port) /
#         Raw(load="UPDATE")
#     )
#     sendp(packet, iface=interface, verbose=False)

# print(f"=== RAM BUFFER SYNC STARTING ON {interface} ===")

# while True:
#     try:
#         # 1. Récupérer les données de Ditto
#         r = requests.get(DITTO_URL, auth=('ditto','ditto'), timeout=2)
        
#         if r.status_code == 200:
#             data = r.json()
            
#             # 2. Écrire le JSON dans la RAM (/dev/shm)
#             with open(RAM_BUFFER_PATH, "w") as f:
#                 json.dump(data, f)
            
#             # 3. Envoyer l'alerte à ns-3 via Scapy
#             send_update_signal()
            
#             print(f"[{time.strftime('%H:%M:%S')}] Signal d'alerte envoyé (JSON mis en RAM)")
            
#         time.sleep(1) # Fréquence de 2Hz (ajustable)

#     except Exception as e:
#         print(f"Erreur : {e}")
#         time.sleep(2)



from scapy.all import *
import json
import requests
import time

# ===============================
# CONFIGURATION (STRICTEMENT IDENTIQUE)
# ===============================
interface = "thetap"
target_ip = "10.1.1.2"
target_mac = "00:00:00:00:00:02" 
target_port = 5000
src_ip = "10.1.1.10"
src_mac = "06:53:88:13:15:81"

SEARCH_URL = "http://127.0.0.1:8080/api/2/search/things"
PARAMS = "namespaces=my5GNetwork&fields=thingId,attributes&option=size(200)"

# RAM_BUFFER_PATH supprimé car on n'écrit plus de fichier
last_data_hash = None

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

# MODIFICATION : On envoie les DATA dans le Raw(load)
def send_update_signal(json_data):
    try:
        packet = (Ether(src=src_mac, dst=target_mac) /
                  IP(src=src_ip, dst=target_ip) /
                  UDP(sport=54321, dport=target_port) /
                  Raw(load=json_data)) # ICI : On met le JSON au lieu de "UPDATE"
        sendp(packet, iface=interface, verbose=False)
    except Exception as e:
        log(f"ERREUR SCAPY: {e}")

def get_data():
    """Récupère les données en un seul appel (max 200 objets)."""
    try:
        r = requests.get(f"{SEARCH_URL}?{PARAMS}", auth=('ditto', 'ditto'), timeout=5)
        if r.status_code == 200:
            return r.json().get('items', [])
        else:
            log(f"Erreur Ditto : {r.status_code}")
            return None
    except Exception as e:
        log(f"Erreur connexion : {e}")
        return None

log(f"=== AGENT DE SYNCHRO (ENVOI DIRECT UDP) SUR {interface} ===")

def sync_initial_config():
    """Récupère les données une fois et crée le fichier pour ns-3."""
    items = get_data()
    if items:
        # On écrit le fichier QUE ns-3 va lire au démarrage (PreParseInitialEntities)
        with open("/dev/shm/ditto_buffer.json", "w") as f:
            json.dump(items, f)
        log(f"✅ Configuration initiale synchronisée : {len(items)} objets écrits dans /dev/shm/ditto_buffer.json")
    else:
        log("❌ Impossible de récupérer la config initiale !")

log(f"=== AGENT DE SYNCHRO (ENVOI DIRECT UDP) SUR {interface} ===")

sync_initial_config() 



while True:
    items = get_data()
    
    if items is not None:
        ids = [i.get('thingId') for i in items]
        log(f"DONNÉES GET : {len(items)} objets reçus.")

        # 2. COMPARAISON (HASH)
        current_data_str = json.dumps(items, sort_keys=True)
        current_hash = hash(current_data_str)
        
        if current_hash != last_data_hash:
            # --- MODIFICATION : PLUS DE FICHIER ---
            # On envoie directement la chaîne JSON par Scapy
            send_update_signal(current_data_str)
            # --------------------------------------
            
            log(" >>> CHANGEMENT DÉTECTÉ : Données envoyées DIRECTEMENT par UDP à ns-3.")
            last_data_hash = current_hash
        else:
            log(" --- Stable (aucun changement).")
    
    print("-" * 50, flush=True)
    time.sleep(1.0) # Fréquence de rafraîchissement