# import socket
# import json
# import os

# # --- PT CONFIGURATION ---
# LISTEN_IP = "198.19.20.1"
# LISTEN_PORT = 8000 
# # VERIFIE BIEN CE CHEMIN :
# SOURCE_JSON_FILE = "../simulations/network_state.json" 

# def get_last_snapshot(filepath):
#     try:
#         if not os.path.exists(filepath):
#             print(f"[!] Erreur: Le fichier {filepath} n'existe pas.")
#             return None
        
#         # Vérifier si le fichier est vide
#         if os.path.getsize(filepath) == 0:
#             print(f"[!] Erreur: Le fichier {filepath} est totalement vide (0 octets).")
#             return None

#         with open(filepath, 'r') as f:
#             data = json.load(f)
            
#             # Cas 1 : C'est une liste [{}, {}] -> on prend le dernier
#             if isinstance(data, list):
#                 if len(data) > 0:
#                     return data[-1]
#                 else:
#                     print("[!] Erreur: La liste JSON est vide [].")
#                     return None
            
#             # Cas 2 : C'est un objet unique {} -> on le prend directement
#             elif isinstance(data, dict):
#                 return data
            
#             else:
#                 print(f"[!] Erreur: Format JSON inconnu ({type(data)}).")
#                 return None

#     except json.JSONDecodeError:
#         print(f"[!] Erreur: Le fichier {filepath} contient du texte qui n'est pas du JSON valide.")
#         return None
#     except Exception as e:
#         print(f"[!] Erreur de lecture: {e}")
#         return None

# def main():
#     sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#     # Option pour libérer le port immédiatement en cas de crash
#     sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
#     try:
#         sock.bind((LISTEN_IP, LISTEN_PORT))
#         print(f"[*] PT Responder listening on {LISTEN_IP}:{LISTEN_PORT}...")
#     except Exception as e:
#         print(f"[!] Erreur de Bind: {e}")
#         return

#     while True:
#         data, addr = sock.recvfrom(65535)
#         print(f"[?] Requête reçue de {addr}") # Debug trace
#         try:
#             request = json.loads(data.decode())
#             if request.get("cmd") == "GET_STATE":
#                 snapshot = get_last_snapshot(SOURCE_JSON_FILE)
#                 if snapshot:
#                     snapshot["request_id"] = request.get("id")
#                     sock.sendto(json.dumps(snapshot).encode(), addr)
#                     print(f"[PT >] Snapshot envoyé pour ID: {request.get('id')}")
#                 else:
#                     # Envoyer une erreur au collector au lieu de rien
#                     sock.sendto(json.dumps({"error": "no_data"}).encode(), addr)
#         except Exception as e:
#             print(f"[!] Erreur boucle: {e}")

# if __name__ == "__main__":
#     main()


import socket
import json
import os
import threading
import time

# ===========================================================================
# CONFIGURATION GÉNÉRALE (VÉRIFIE TES CHEMINS !)
# ===========================================================================

# --- Configuration PHYSICAL TWIN (PT) ---
PT_LISTEN_IP = "198.19.20.1"
PT_LISTEN_PORT = 8000 
PT_JSON_FILE = "/home/abdessamed/simu5g_project/FiveG_network/simulations/network_state.json" 

# --- Configuration DIGITAL TWIN (DT) ---
DT_LISTEN_IP = "198.19.10.1"
DT_LISTEN_PORT = 9900
DT_JSON_FILE = "/home/abdessamed/ns-3-dev/build/dt_state.json" 

# ===========================================================================
# LOGIQUE DE LECTURE UNIFIÉE
# ===========================================================================

def get_last_snapshot(filepath, label):
    """Lit le dernier snapshot d'un fichier JSON de manière robuste."""
    try:
        if not os.path.exists(filepath):
            return None
        
        if os.path.getsize(filepath) == 0:
            return None

        with open(filepath, 'r') as f:
            data = json.load(f)
            
            # Si c'est une liste [{}, {}], on prend le dernier élément
            if isinstance(data, list):
                if len(data) > 0:
                    return data[-1]
                return None
            
            # Si c'est un objet unique {}, on le prend directement
            elif isinstance(data, dict):
                return data
            
            return None

    except json.JSONDecodeError:
        # Arrive souvent si le simulateur écrit en même temps qu'on lit
        return None 
    except Exception as e:
        print(f"[{label} ERROR] Lecture: {e}")
        return None

# ===========================================================================
# BOUCLE DE RÉPONSE (FONCTION EXÉCUTÉE PAR CHAQUE THREAD)
# ===========================================================================

def responder_loop(ip, port, filepath, label):
    """Gère les requêtes UDP pour un jumeau spécifique."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        sock.bind((ip, port))
        print(f"[*] {label} Responder active sur {ip}:{port}")
    except Exception as e:
        print(f"[!] {label} ERREUR BIND sur {ip}:{port} : {e}")
        return

    while True:
        try:
            # Attente d'une requête (bloquant)
            data, addr = sock.recvfrom(65535)
            request = json.loads(data.decode())
            
            if request.get("cmd") == "GET_STATE":
                request_id = request.get("id", "unknown")
                snapshot = get_last_snapshot(filepath, label)
                
                if snapshot:
                    # On injecte l'ID de requête pour la corrélation
                    snapshot["request_id"] = request_id
                    
                    # Envoi de la réponse
                    response_data = json.dumps(snapshot).encode()
                    sock.sendto(response_data, addr)
                    
                    # Log compact pour ne pas saturer la console
                    print(f"[{label} >] Sent ID: {request_id} to {addr}")
                else:
                    # Envoi d'un message d'erreur si pas de data
                    error_msg = json.dumps({"request_id": request_id, "error": "no_data"}).encode()
                    sock.sendto(error_msg, addr)

        except Exception as e:
            print(f"[{label} LOOP ERROR]: {e}")

# ===========================================================================
# LANCEMENT DES THREADS
# ===========================================================================

if __name__ == "__main__":
    print("="*60)
    print("      DITTO UNIFIED RESPONDER (PT & DT SYNCHRONIZED)")
    print("="*60)

    # Création des deux threads
    thread_pt = threading.Thread(
        target=responder_loop, 
        args=(PT_LISTEN_IP, PT_LISTEN_PORT, PT_JSON_FILE, "PT"),
        daemon=True # Le thread meurt si le script principal s'arrête
    )

    thread_dt = threading.Thread(
        target=responder_loop, 
        args=(DT_LISTEN_IP, DT_LISTEN_PORT, DT_JSON_FILE, "DT"),
        daemon=True
    )

    # Démarrage
    thread_pt.start()
    thread_dt.start()

    try:
        # Boucle principale pour maintenir le script en vie
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[!] Arrêt des répondeurs...")