import socket
import json
import os
import time
import subprocess
import sys

# --- CONFIGURATION PAR DÉFAUT ---
DEFAULT_FREQ = 200
UDP_IP_DEST = "10.255.0.1"
UDP_IP_SRC = "10.255.0.1"
UDP_PORT = 9999
INTERFACE = "veth-sender"

# Chemins
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
    print(f"\n[TC] Application du profil : {config['desc']}")
    subprocess.run(f"tc qdisc del dev {INTERFACE} root 2>/dev/null || true", shell=True)
    cmd = f"tc qdisc add dev {INTERFACE} root netem delay {config['delay']} loss {config['loss']} rate {config['rate']}"
    if config.get("corrupt") and config["corrupt"] != "0%":
        cmd += f" corrupt {config['corrupt']}"
    subprocess.run(cmd, shell=True)

def main():
    # 1. Gestion de la fréquence via Argument (ex: python3 script.py 50)
    global_freq = DEFAULT_FREQ
    if len(sys.argv) > 1:
        try:
            global_freq = int(sys.argv[1])
        except ValueError:
            print(f"Usage: sudo python3 {sys.argv[0]} [frequency_hz]")
    
    if os.getuid() != 0:
        print("❌ Erreur: sudo requis pour TC et l'accès à l'interface réseau."); sys.exit(1)

    # Initialisation du log
    with open(SENT_LOG_PATH, "w") as f:
        f.write("SnapshotID\tTimestampMS\tSimTime\tStatus\n")

    print(f"\n🚀 DÉMARRAGE ÉMETTEUR - Fréquence : {global_freq} Hz (Intervalle : {1000/global_freq:.2f} ms)")
    
    for k, v in NETWORK_PROFILES.items(): print(f" {k}. {v['desc']}")
    choice = input("\nChoix du profil réseau : ")
    if choice in NETWORK_PROFILES:
        apply_network_conditions(NETWORK_PROFILES[choice])
    else: 
        print("❌ Choix invalide."); return

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP_SRC, 0))
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, INTERFACE.encode())

    last_sent_t = -1.0
    snapshot_id = 0
    interval = 1.0 / global_freq

    print(f"[*] Envoi vers {UDP_IP_DEST}:{UDP_PORT}. Ctrl+C pour quitter.")

    try:
        while True:
            start_loop = time.time()
            
            if os.path.exists(JSON_PATH):
                try:
                    with open(JSON_PATH, "r") as f:
                        data = json.load(f)
                        last_state = data[-1] if isinstance(data, list) else data
                        
                        current_t = float(last_state.get("timestamp", 0))

                        # On n'envoie que si c'est un nouveau temps de simulation
                        if current_t > last_sent_t:
                            # Construction du JSON "LITE" (Clés n, f, s, d, sz, i)
                            nodes_lite = []
                            for n in last_state.get("nodes", []):
                                nodes_lite.append({
                                    "id": n["id"],
                                    "x": n["x"],
                                    "y": n["y"],
                                    "z": n.get("z", 1.5),
                                    "sinr_dl": n.get("sinr_dl", 0),  # 
                                    "sinr_ul": n.get("sinr_ul", 0),  #
                                    # "speed": n.get("speed", 0)
                                })

                            flows_lite = []
                            for f in last_state.get("flows", []):
                                flows_lite.append({
                                    "s": f["src"],
                                    "d": f["dst"],
                                    "thr": f.get("throughput", 0),
                                    "sz": f.get("packet_size", 1450),
                                    "i": f.get("interval", 0.001)
                                })

                            packet = {
                                "t": current_t,
                                "n": nodes_lite,
                                "f": flows_lite
                            }
                            
                            # Envoi UDP
                            sock.sendto(json.dumps(packet).encode(), (UDP_IP_DEST, UDP_PORT))
                            
                            # Log local pour analyse de synchro
                            snapshot_id += 1
                            ts_ms = int(time.time() * 1000)
                            with open(SENT_LOG_PATH, "a") as f:
                                f.write(f"{snapshot_id}\t{ts_ms}\t{current_t}\tSENT\n")
                            
                            last_sent_t = current_t
                            # Affichage discret toutes les 10 envois
                            if snapshot_id % 10 == 0:
                                print(f" [TX] ID:{snapshot_id} | t={current_t} envoyé.")

                except (json.JSONDecodeError, IndexError, KeyError):
                    # Fichier en cours d'écriture ou vide, on ignore et on re-essaie
                    pass 

            # RÉGLAGE DE LA FRÉQUENCE : Calcul précis du sommeil
            elapsed = time.time() - start_loop
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n🛑 Arrêt Émetteur.")
    finally:
        sock.close()

if __name__ == "__main__":
    main()