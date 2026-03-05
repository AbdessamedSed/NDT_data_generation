import socket
import json
import os

# --- PT CONFIGURATION ---
LISTEN_IP = "192.168.10.1"
LISTEN_PORT = 8888  
SOURCE_JSON_FILE = "../simulations/network_state.json" 

def get_last_snapshot(filepath):
    try:
        if not os.path.exists(filepath): return None
        with open(filepath, 'r') as f:
            data = json.load(f)
            return data[-1] if isinstance(data, list) and data else None
    except Exception as e:
        print(f"[!] Read Error: {e}")
        return None

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LISTEN_IP, LISTEN_PORT))
    print(f"[*] PT Responder listening on {LISTEN_IP}:{LISTEN_PORT}...")

    while True:
        data, addr = sock.recvfrom(65535)
        try:
            request = json.loads(data.decode())
            if request.get("cmd") == "GET_STATE":
                snapshot = get_last_snapshot(SOURCE_JSON_FILE)
                if snapshot:
                    snapshot["request_id"] = request.get("id")
                    sock.sendto(json.dumps(snapshot).encode(), addr)
                    print(f"[PT >] Sent Snapshot ID: {request.get('id')}")
        except Exception as e:
            print(f"[!] Error: {e}")

if __name__ == "__main__":
    main()