import socket
import json
import os

# --- CONFIGURATION ---
LISTEN_IP = "172.16.0.1"
LISTEN_PORT = 9999
DATA_FILE = "../../build/dtConnector_all_positions_ns3.txt"

# Structure of your .txt file (Header names)
HEADERS = [
    "ue[0]_x", "ue[0]_y", "ue[0]_z", "ue[1]_x", "ue[1]_y", "ue[1]_z",
    "ue[2]_x", "ue[2]_y", "ue[2]_z", "ue[3]_x", "ue[3]_y", "ue[3]_z", 
    "gnb_x", "gnb_y", "gnb_z"
]

def get_last_line(filepath):
    """Jumps to the end of the file and reads the last line."""
    try:
        if not os.path.exists(filepath):
            print(f"[DEBUG-FILE] FAILED: File does not exist at {os.path.abspath(filepath)}")
            return None
        
        with open(filepath, 'rb') as f:
            f.seek(0, os.SEEK_END)
            filesize = f.tell()
            if filesize == 0:
                print(f"[DEBUG-FILE] FAILED: File is empty (0 bytes).")
                return None
            
            # Start moving backwards from the end
            offset = -2
            # Handle files that might only have one line
            if filesize < abs(offset):
                f.seek(0)
                return f.readline().decode().strip()

            f.seek(offset, os.SEEK_END)
            # Walk back until we find a newline
            while f.read(1) != b'\n':
                offset -= 1
                try:
                    f.seek(offset, os.SEEK_END)
                except OSError: # Reached start of file
                    f.seek(0)
                    break
            
            last_line = f.readline().decode().strip()
            print(f"[DEBUG-FILE] SUCCESS: Read {len(last_line)} characters from file.")
            return last_line
            
    except Exception as e:
        print(f"[DEBUG-FILE] ERROR: Exception while reading: {e}")
        return None

def main():
    # Show absolute path on startup so you know exactly where the script is looking
    print("="*50)
    print(f"[*] Starting Responder...")
    print(f"[*] Target Data File: {os.path.abspath(DATA_FILE)}")
    print(f"[*] File status: {'EXISTS' if os.path.exists(DATA_FILE) else 'NOT FOUND'}")
    print("="*50)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((LISTEN_IP, LISTEN_PORT))
    except OSError as e:
        print(f"[!] BIND ERROR: {e}. Check if IP {LISTEN_IP} exists on your system.")
        return

    print(f"[*] Server listening on {LISTEN_IP}:{LISTEN_PORT}...")

    while True:
        data, addr = sock.recvfrom(1024)
        print(f"\n[RECEIVED] Request from {addr}")
        
        try:
            # 1. Parse Request JSON
            decoded_data = data.decode()
            print(f"  └─ Raw Data: {decoded_data}")
            
            request = json.loads(decoded_data)
            request_id = request.get("id", "unknown")
            cmd = request.get("cmd", "none")

            if cmd == "GET_STATE":
                print(f"  └─ Command: GET_STATE (ID: {request_id})")
                
                raw_line = get_last_line(DATA_FILE)
                
                if raw_line:
                    # 2. Parse the .txt line (split by tabs)
                    values = raw_line.split('\t')
                    print(f"  └─ Values found in file: {len(values)} columns.")
                    
                    if len(values) != len(HEADERS):
                        print(f"  [!] WARNING: Header mismatch! Expected {len(HEADERS)}, got {len(values)}.")

                    # 3. Create the JSON Response
                    response_dict = {HEADERS[i]: values[i] for i in range(min(len(values), len(HEADERS)))}
                    response_dict["id"] = request_id
                    
                    # 4. Send JSON response
                    json_response = json.dumps(response_dict)
                    sock.sendto(json_response.encode(), addr)
                    print(f"  [SENT] Response ID {request_id} to {addr}")
                else:
                    print(f"  [!] ABORT: No data read from file. Sending nothing back.")
            else:
                print(f"  [!] Unknown command: {cmd}")

        except json.JSONDecodeError:
            print(f"  [!] ERROR: Received invalid JSON format.")
        except Exception as e:
            print(f"  [!] ERROR processing request: {e}")

if __name__ == "__main__":
    main()