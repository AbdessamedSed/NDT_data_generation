import socket
import json
import os

# --- CONFIGURATION ---
LISTEN_IP = "10.255.255.1"
LISTEN_PORT = 9999
DATA_FILE = "../simulations/dtConnector_all_positions.txt"

# Structure of your .txt file (Header names)
HEADERS = [
    "sim_time", "ue[0]_x", "ue[0]_y", "ue[0]_z", "ue[1]_x", "ue[1]_y", "ue[1]_z",
    "ue[2]_x", "ue[2]_y", "ue[2]_z", "ue[3]_x", "ue[3]_y", "ue[3]_z", "gnb_x", "gnb_y", "gnb_z"
]

def get_last_line(filepath):
    try:
        if not os.path.exists(filepath): return None
        with open(filepath, 'rb') as f:
            f.seek(0, os.SEEK_END)
            if f.tell() == 0: return None # Empty file
            f.seek(-2, os.SEEK_END)
            while f.read(1) != b'\n':
                f.seek(-2, os.SEEK_CUR)
            last_line = f.readline().decode().strip()
        return last_line
    except Exception:
        return None

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LISTEN_IP, LISTEN_PORT))
    print(f"[*] Server listening on {LISTEN_IP}:{LISTEN_PORT}...")

    while True:
        data, addr = sock.recvfrom(1024)
        try:
            # 1. Parse Request JSON
            request = json.loads(data.decode())
            request_id = request.get("id", "unknown")

            if request.get("cmd") == "GET_STATE":
                raw_line = get_last_line(DATA_FILE)
                if raw_line:
                    # 2. Parse the .txt line (split by tabs)
                    values = raw_line.split('\t')
                    
                    # 3. Create the JSON Response
                    # Map values to headers and include the original ID
                    response_dict = {HEADERS[i]: values[i] for i in range(len(values))}
                    response_dict["id"] = request_id
                    
                    # 4. Send JSON response
                    sock.sendto(json.dumps(response_dict).encode(), addr)
                    print(f"[>] Sent ID: {request_id} to {addr}")
                
                else:
                    print(f"[!] File {DATA_FILE} is empty or not found! Sending nothing.")

        except Exception as e:
            print(f"[!] Error processing request: {e}")

if __name__ == "__main__":
    main()