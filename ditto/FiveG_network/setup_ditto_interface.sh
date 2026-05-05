#!/bin/bash

NS_NAME="ns-dt"
VETH_SENDER="veth-sender"
VETH_RECEIVER="veth-receiver"

# IPs
IP_SENDER="10.255.0.1"
IP_RECEIVER="10.255.0.2"

echo "[*] Nettoyage de l'ancienne configuration..."
sudo ip netns del $NS_NAME 2>/dev/null
sudo ip link del $VETH_SENDER 2>/dev/null

echo "[*] Création du Namespace : $NS_NAME"
sudo ip netns add $NS_NAME

echo "[*] Création du lien VETH (Câble virtuel)..."
sudo ip link add $VETH_SENDER type veth peer name $VETH_RECEIVER

echo "[*] Connexion du Receiver au Namespace..."
sudo ip link set $VETH_RECEIVER netns $NS_NAME

echo "[*] Configuration de l'IP du Sender ($IP_SENDER)..."
sudo ip addr add $IP_SENDER/24 dev $VETH_SENDER
sudo ip link set $VETH_SENDER up

echo "[*] Configuration de l'IP du Receiver ($IP_RECEIVER) dans le Namespace..."
sudo ip netns exec $NS_NAME ip addr add $IP_RECEIVER/24 dev $VETH_RECEIVER
sudo ip netns exec $NS_NAME ip link set $VETH_RECEIVER up
sudo ip netns exec $NS_NAME ip link set lo up

echo "[OK] Environnement prêt !"
echo "-------------------------------------------------------"
echo "1. Lance le Receiver : sudo ip netns exec $NS_NAME python3 ditto_receiver.py"
echo "2. Lance le Sender   : sudo python3 ditto_sender.py"
echo "TRÈS IMPORTANT: Pour exécuter après le script de ditto receiver, utiliser : sudo ip netns exec ns-dt python3 omnetpp_ditto_receiver.py"
echo "-------------------------------------------------------"
