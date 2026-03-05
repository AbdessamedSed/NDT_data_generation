#!/bin/bash

# Check if the script is run as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)"
   exit 1
fi

echo "[*] Loading dummy network module..."
modprobe dummy

# 1. Create the Responder Interface (SENDER_IP in your first script)
echo "[*] Creating interface for Responder (172.16.0.1)..."
ip link add dev dt-responder type dummy
ip addr add 172.16.0.1/24 dev dt-responder
ip link set dt-responder up

# 2. Create the Collector Interface (CLIENT_IP in your first script)
echo "[*] Creating interface for Collector (172.16.0.2)..."
ip link add dev dt-collector type dummy
ip addr add 172.16.0.2/24 dev dt-collector
ip link set dt-collector up

echo "[+] Interfaces created successfully!"
echo "---------------------------------------"
ip addr show | grep -E "dt-responder|dt-collector"
echo "---------------------------------------"
echo "[!] IMPORTANT: Ensure your Python scripts use these IPs:"
echo "    Responder (Server) should bind to: 172.16.0.1"
echo "    Collector (Client) should bind to: 172.16.0.2"