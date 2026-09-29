package src;

import inet.node.inet.StandardHost;
import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.visualizer.common.MobilityVisualizer;

import simu5g.nodes.NrUe;
import simu5g.nodes.gNodeB;
import simu5g.nodes.Upf;
import simu5g.common.binder.Binder;
import simu5g.world.radio.LteChannelControl;
import simu5g.common.carrierAggregation.CarrierAggregation;

import src.DTConnector;

network HandoverTestNetwork
{
    parameters:
        @display("bgb=1200,700");

    types:
        channel CoreLink extends ned.DatarateChannel
        {
            delay = 0.1ms;
            datarate = 10Gbps;
        }

        channel X2Link extends ned.DatarateChannel
        {
            delay = 0.1ms;
            datarate = 10Gbps;
        }

    submodules:
        channelControl: LteChannelControl {
            @display("p=50,50");
        }

        configurator: Ipv4NetworkConfigurator {
            @display("p=50,120");
        }

        binder: Binder {
            @display("p=50,190");
        }

        carrierAggregation: CarrierAggregation {
            @display("p=50,260");
        }

        server: StandardHost {
            @display("p=100,400");
        }

        upf: Upf {
            @display("p=300,400");
        }

        gnb[2]: gNodeB {
            @display("p=600,250");
        }

        ue: NrUe {
            @display("p=600,550");
        }

        dtConnector: DTConnector {
            @display("p=100,550");
        }

        visualizer: MobilityVisualizer {
            @display("p=50,330");
        }

    connections:
        server.pppg++ <--> CoreLink <--> upf.filterGate;

        upf.pppg++ <--> CoreLink <--> gnb[0].ppp;
        upf.pppg++ <--> CoreLink <--> gnb[1].ppp;

        // X2 link required for the handover procedure
        gnb[0].x2++ <--> X2Link <--> gnb[1].x2++;
}
