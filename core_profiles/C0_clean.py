#!/usr/bin/env core-python

"""
C0_clean
Nominal PT-to-DT communication profile.

Topology:
    OMNeT gateway <-> EMANE RF Pipe <-> Ditto gateway

Purpose:
    Clean/reference communication condition.

No artificial packet loss, no background traffic and no intentional
congestion are introduced in this profile. RTT, jitter, packet loss,
goodput and synchronization overhead must be measured from the resulting
communication rather than imposed as experiment outputs.
"""

import time

from core.api.grpc import client
from core.api.grpc.wrappers import NodeType, Position
from core.emane.models.rfpipe import EmaneRfPipeModel


def main():
    iface_helper = client.InterfaceHelper(
        ip4_prefix="10.100.0.0/24"
    )

    core = client.CoreGrpcClient()
    core.connect()

    session = core.create_session()

    # ------------------------------------------------------------------
    # EMANE wireless network
    # ------------------------------------------------------------------
    emane = session.add_node(
        1,
        _type=NodeType.EMANE,
        position=Position(x=200, y=200),
        emane=EmaneRfPipeModel.name,
    )

    # ------------------------------------------------------------------
    # PT-side gateway
    # ------------------------------------------------------------------
    pt = session.add_node(
        2,
        name="omnet-gateway",
        model="host",
        position=Position(x=100, y=200),
    )

    # ------------------------------------------------------------------
    # DT/Ditto-side gateway
    # ------------------------------------------------------------------
    dt = session.add_node(
        3,
        name="ditto-gateway",
        model="host",
        position=Position(x=300, y=200),
    )

    pt_iface = iface_helper.create_iface(
        node_id=pt.id,
        iface_id=0,
        name="eth0",
    )

    dt_iface = iface_helper.create_iface(
        node_id=dt.id,
        iface_id=0,
        name="eth0",
    )

    session.add_link(
        node1=pt,
        node2=emane,
        iface1=pt_iface,
    )

    session.add_link(
        node1=dt,
        node2=emane,
        iface1=dt_iface,
    )

    # C0 intentionally uses the nominal RF Pipe configuration.
    # Impairments will be introduced only in C1/C2/C3.
    core.start_session(session)

    print("=" * 60)
    print("CORE/EMANE profile: C0_clean")
    print(f"CORE session ID: {session.id}")
    print("PT gateway   : 10.100.0.2")
    print("Ditto gateway: 10.100.0.3")
    print("Background traffic: NONE")
    print("Artificial loss   : NONE")
    print("Intentional congestion: NONE")
    print("=" * 60)

    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping C0 CORE session...")
        core.delete_session(session.id)


if __name__ == "__main__":
    main()
