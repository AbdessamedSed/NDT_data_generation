#!/bin/bash

# Vérifier si le script est lancé en tant que root
if [[ $EUID -ne 0 ]]; then
   echo "Ce script doit être lancé avec sudo"
   exit 1
fi

echo "[*] Nettoyage des anciennes interfaces..."
ip link delete vnet-dt 2>/dev/null
ip link delete vnet-pt 2>/dev/null

# --- CONFIGURATION DU RÉSEAU DIGITAL TWIN (198.19.10.x) ---
echo "[*] Configuration de vnet-dt (Digital Twin)..."
modprobe dummy
ip link add dev vnet-dt type dummy
ip addr add 198.19.10.1/24 dev vnet-dt
ip addr add 198.19.10.2/24 dev vnet-dt
ip link set vnet-dt up

# --- CONFIGURATION DU RÉSEAU PHYSICAL TWIN (198.19.20.x) ---
echo "[*] Configuration de vnet-pt (Physical Twin)..."
ip link add dev vnet-pt type dummy
ip addr add 198.19.20.1/24 dev vnet-pt
ip addr add 198.19.20.2/24 dev vnet-pt
ip link set vnet-pt up

echo "-------------------------------------------------------"
echo "[+] INTERFACES CRÉÉES AVEC SUCCÈS"
echo "-------------------------------------------------------"
echo " DIGITAL TWIN (vnet-dt):"
echo "   - Responder: 198.19.10.1"
echo "   - Collector: 198.19.10.2"
echo ""
echo " PHYSICAL TWIN (vnet-pt):"
echo "   - Responder: 198.19.20.1"
echo "   - Collector: 198.19.20.2"
echo "-------------------------------------------------------"

# Affichage pour vérification
ip addr show vnet-dt | grep "inet "
ip addr show vnet-pt | grep "inet "
