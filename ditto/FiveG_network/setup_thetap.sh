#!/bin/bash
ip link show thetap >/dev/null 2>&1 || ip tuntap add dev thetap mode tap
ip link set thetap up
ip addr show thetap | grep -q "10.1.1.10/24" || ip addr add 10.1.1.10/24 dev thetap
