#!/bin/bash

if [[ $EUID -ne 0 ]]; then
   echo "Please run as root (sudo)"
   exit 1
fi

echo "[*] Creating Physical Twin Interfaces..."

# 1. Interface for Physical Responder (The "Real" System)
ip link add dev pt-responder type dummy
ip addr add 192.168.10.1/24 dev pt-responder
ip link set pt-responder up

# 2. Interface for Physical Collector
ip link add dev pt-collector type dummy
ip addr add 192.168.10.2/24 dev pt-collector
ip link set pt-collector up

echo "[+] Physical Twin Interfaces (192.168.10.1 & 192.168.10.2) are UP."
