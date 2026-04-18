#!/bin/bash

# 1. Nettoyage
sudo ip netns del ns-sender 2>/dev/null
sudo ip netns del ns-receiver 2>/dev/null
sudo ip link del br-ditto 2>/dev/null

# 2. Créer le Bridge (L'Hôte devient 10.255.0.1)
sudo ip link add name br-ditto type bridge
sudo ip addr add 10.255.0.1/24 dev br-ditto
sudo ip link set br-ditto up

# 3. Créer les Namespaces
sudo ip netns add ns-sender
sudo ip netns add ns-receiver

# 4. Connecter SENDER (veth-s-ns <-> veth-s-br)
sudo ip link add veth-sender type veth peer name veth-s-br
sudo ip link set veth-sender netns ns-sender
sudo ip link set veth-s-br master br-ditto
sudo ip netns exec ns-sender ip addr add 10.255.0.10/24 dev veth-sender
sudo ip netns exec ns-sender ip link set veth-sender up
sudo ip netns exec ns-sender ip link set lo up
sudo ip link set veth-s-br up

# 5. Connecter RECEIVER (veth-receiver <-> veth-r-br)
sudo ip link add veth-receiver type veth peer name veth-r-br
sudo ip link set veth-receiver netns ns-receiver
sudo ip link set veth-r-br master br-ditto
sudo ip netns exec ns-receiver ip addr add 10.255.0.2/24 dev veth-receiver
sudo ip netns exec ns-receiver ip link set veth-receiver up
sudo ip netns exec ns-receiver ip link set lo up
sudo ip link set veth-r-br up

# 6. ROUTAGE : Autoriser la communication entre namespaces via le bridge
sudo iptables -A FORWARD -i br-ditto -o br-ditto -j ACCEPT

echo "✅ Configuration terminée. Hôte Ditto: 10.255.0.1 | Sender: 10.255.0.10 | Receiver: 10.255.0.2"
