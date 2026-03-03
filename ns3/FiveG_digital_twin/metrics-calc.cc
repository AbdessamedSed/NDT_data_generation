
#include "metrics-calc.h"

double g_captureInterval = 0.5;
std::map<std::string, Ptr<Node>> thingIdToNode;
std::map<uint32_t, UeRadioTable> table_radio_5g;
std::map<uint16_t, uint32_t> rnti_to_nodeid;
std::map<std::string, FlowInfo> active_flows;


void TraceMacDlThroughput(uint32_t nodeId, Ptr<const Packet> packet) {
    table_radio_5g[nodeId].bytesRxDl += packet->GetSize();
    std::cout << "\033[1;32m[RECEPTION-MAC]\033[0m Node " << nodeId << " received " << packet->GetSize() << " bytes" << std::endl;
}

// Capturé au niveau du gNB pour l'Uplink
void TraceMacUlThroughput(uint16_t rnti, Ptr<const Packet> packet) {
    if (rnti_to_nodeid.count(rnti)) {
        uint32_t nodeId = rnti_to_nodeid[rnti];
        table_radio_5g[nodeId].bytesRxUl += packet->GetSize();
        // Print si on trouve le noeud
        std::cout << "\033[1;34m[UL-DATA]\033[0m RNTI " << rnti << " -> Node " << nodeId 
                  << " | Reçu: " << packet->GetSize() << " octets" << std::endl;
    } else {
        // C'EST ICI QUE CA BLOQUE SOUVENT
        static std::map<uint16_t, bool> warned_rnti;
        if (!warned_rnti[rnti]) {
            std::cout << "\033[1;31m[UL-ERROR]\033[0m Paquet reçu pour RNTI " << rnti 
                      << " mais ce RNTI n'est PAS dans la map rnti_to_nodeid !" << std::endl;
            warned_rnti[rnti] = true; 
        }
    }
}

// // Fonction pour calculer le débit toutes les secondes
// void ComputeThroughput() {
//     for (auto & [nodeId, metrics] : table_radio_5g) {
//         metrics.macThroughputDl = (metrics.bytesRxDl * 8.0) / (1e6 * g_captureInterval);
//         metrics.macThroughputUl = (metrics.bytesRxUl * 8.0) / (1e6 * g_captureInterval);
        
//         // PRINT DE PREUVE SI TRAFIC
//         if (metrics.macThroughputDl > 0 || metrics.macThroughputUl > 0) {
//             std::cout << "\033[1;32m[MAC-STATS]\033[0m Node " << nodeId 
//                       << " | Thr DL: " << metrics.macThroughputDl << " Mbps"
//                       << " | Thr UL: " << metrics.macThroughputUl << " Mbps" << std::endl;
//         }

//         metrics.bytesRxDl = 0; metrics.bytesRxUl = 0;
//     }
//     Simulator::Schedule(Seconds(g_captureInterval), &ComputeThroughput);
// }

void UpdateDlSinrTable(uint32_t nodeId, uint16_t cellId, uint16_t rnti, double sinr, uint16_t bwpId) {
    table_radio_5g[nodeId].dlSinr = sinr;
    // Print de debug pour confirmer que ça marche
    std::cout << "\033[1;36m[PHY-DL]\033[0m Node: " << nodeId 
              << " | RNTI: " << rnti 
              << " | SINR: " << sinr << " dB" << std::endl;
}


void UpdateUlSinrTable(uint64_t rnti, SpectrumValue& sinr, SpectrumValue& interference) {
    uint16_t rnti16 = static_cast<uint16_t>(rnti);
    if (rnti_to_nodeid.count(rnti16)) {
        uint32_t nodeId = rnti_to_nodeid[rnti16];

        double sumSinr = 0;
        uint32_t count = 0;
        for (auto it = sinr.ConstValuesBegin(); it != sinr.ConstValuesEnd(); ++it) {
            sumSinr += (*it);
            count++;
        }

        if (count > 0) {
            double avgSinrLin = sumSinr / count;
            // CONVERSION EN dB : INDISPENSABLE
            double avgSinrDb = 10 * std::log10(avgSinrLin);
            
            table_radio_5g[nodeId].ulSinr = avgSinrDb;
            std::cout << "\033[1;35m[PHY-UL]\033[0m Node " << nodeId 
                      << " | SINR: " << avgSinrDb << " dB" << std::endl;
        }
    }
}



void TracePhyStatsDl(uint32_t nodeId, uint16_t rnti, uint16_t bwpId, uint32_t nCbs, uint32_t nPassedCbs) {
    if (nCbs > 0) {
        table_radio_5g[nodeId].blerDl = 1.0 - ((double)nPassedCbs / (double)nCbs);
        if (nCbs > nPassedCbs) table_radio_5g[nodeId].packetLossDl += (nCbs - nPassedCbs);
    }
}

void TracePhyStatsUl(uint16_t rnti, uint16_t bwpId, uint32_t nCbs, uint32_t nPassedCbs) {
    if (rnti_to_nodeid.count(rnti) && nCbs > 0) {
        uint32_t nodeId = rnti_to_nodeid[rnti];
        table_radio_5g[nodeId].blerUl = 1.0 - ((double)nPassedCbs / (double)nCbs);
        if (nCbs > nPassedCbs) table_radio_5g[nodeId].packetLossUl += (nCbs - nPassedCbs);
    }
}


void ComputeThroughput(Ptr<NrHelper> nrHelper) {
    double interval = 1.0; // 1 second for stable reading
    Ptr<NrBearerStatsCalculator> bearerStats = nrHelper->GetRlcStatsCalculator();
    if (!bearerStats) {
        Simulator::Schedule(Seconds(interval), &ComputeThroughput, nrHelper);
        return;
    }

    // Static maps to remember the previous state for Delta calculation
    static std::map<uint64_t, uint64_t> lastDlBytes;
    static std::map<uint64_t, uint64_t> lastUlBytes;

    std::cout << "\n\033[1;32m--- 5G THROUGHPUT (Mbps) ---\033[0m" << std::endl;

    for (uint32_t i = 0; i < 4; ++i) {
        uint64_t imsi = i + 3; 
        uint64_t currentDl = 0;
        uint64_t currentUl = 0;

        // Sum data across LCIDs 1-5 (Signaling + Data)
        for (uint8_t lcid = 1; lcid <= 5; ++lcid) {
            currentDl += bearerStats->GetDlRxData(imsi, lcid);
            currentUl += bearerStats->GetUlRxData(imsi, lcid);
        }
        
        // Calculate Deltas
        double dlThr = ((currentDl - lastDlBytes[imsi]) * 8.0) / (interval * 1e6);
        double ulThr = ((currentUl - lastUlBytes[imsi]) * 8.0) / (interval * 1e6);

        // Save current state for next time
        lastDlBytes[imsi] = currentDl;
        lastUlBytes[imsi] = currentUl;

        uint32_t nodeId = i + 3;
        std::cout << "Node " << nodeId << " | DL: " << std::fixed << std::setprecision(5) << dlThr 
                  << " Mbps | UL: " << std::fixed << std::setprecision(5) << ulThr << " Mbps" << std::endl;

        // Update Snapshot Table
        if (table_radio_5g.count(nodeId)) {
            table_radio_5g[nodeId].macThroughputDl = dlThr;
            table_radio_5g[nodeId].macThroughputUl = ulThr;
        }
    }
    Simulator::Schedule(Seconds(interval), &ComputeThroughput, nrHelper);
}


void ComputeLatency(Ptr<NrHelper> nrHelper) {
    double interval = 1.0; 
    Ptr<NrBearerStatsCalculator> bearerStats = nrHelper->GetRlcStatsCalculator();

    if (!bearerStats) {
        Simulator::Schedule(Seconds(interval), &ComputeLatency, nrHelper);
        return;
    }

    std::cout << "\n\033[1;36m--- 5G LATENCY (ms) ---\033[0m" << std::endl;

    for (uint32_t i = 0; i < 4; ++i) {
        uint64_t imsi = i + 3; // Mapping to Node 3, 4, 5, 6
        uint8_t lcid = 3;      // Focus on your main Data Bearer

        // Get the vectors of statistics
        std::vector<double> dlStats = bearerStats->GetDlDelayStats(imsi, lcid);
        std::vector<double> ulStats = bearerStats->GetUlDelayStats(imsi, lcid);

        double dlMaxLat = 0.0;
        double ulMaxLat = 0.0;

        // Safety Check: Vector must have at least 3 elements to access index [2] (Max)
        if (dlStats.size() >= 3) {
            dlMaxLat = dlStats[2] / 1000000.0; // Index 2 is Maximum, convert to ms
        }
        
        if (ulStats.size() >= 3) {
            ulMaxLat = ulStats[2] / 1000000.0; // Index 2 is Maximum, convert to ms
        }

        uint32_t nodeId = i + 3;
        
        if (dlMaxLat > 0 || ulMaxLat > 0) {
            std::cout << "Node " << nodeId << " | DL Max Latency: " << std::fixed << std::setprecision(3) 
                      << dlMaxLat << " ms | UL Max Latency: " << ulMaxLat << " ms" << std::endl;
        } else {
            std::cout << "Node " << nodeId << " | Latency: [No Data Packets Yet]" << std::endl;
        }

        // Update Snapshot Table
        if (table_radio_5g.count(nodeId)) {
            table_radio_5g[nodeId].macDelayDl = dlMaxLat;
            table_radio_5g[nodeId].macDelayUl = ulMaxLat;
        }
    }
    Simulator::Schedule(Seconds(interval), &ComputeLatency, nrHelper);
}


void ComputeDistance(Ptr<NrHelper> nrHelper, NodeContainer gnbNodes) {
    double interval = 1.0; 
    Ptr<NrBearerStatsCalculator> bearerStats = nrHelper->GetRlcStatsCalculator();
    
    if (!bearerStats) {
        Simulator::Schedule(Seconds(interval), &ComputeDistance, nrHelper, gnbNodes);
        return;
    }

    std::cout << "\n\033[1;33m--- 5G GEOMETRY (Distance) ---\033[0m" << std::endl;

    for (uint32_t i = 0; i < 4; ++i) {
        uint32_t ueNodeId = i + 3; 
        uint64_t imsi = i + 3;
        uint8_t lcid = 3; 

        uint16_t servingCellId = bearerStats->GetDlCellId(imsi, lcid);
        double distance = -1.0;

        // DEBUG : Si tu vois 0 ici, c'est que le bearer n'est pas encore actif
        // std::cout << "Node " << ueNodeId << " est sur CellID: " << servingCellId << std::endl;

        for (uint32_t j = 0; j < gnbNodes.GetN(); ++j) {
            Ptr<Node> gnbNode = gnbNodes.Get(j);
            Ptr<NrGnbNetDevice> gnbDev = nullptr;

            for (uint32_t d = 0; d < gnbNode->GetNDevices(); ++d) {
                gnbDev = gnbNode->GetDevice(d)->GetObject<NrGnbNetDevice>();
                if (gnbDev) break;
            }
            
            if (gnbDev && (gnbDev->GetCellId() == servingCellId)) {
                Ptr<MobilityModel> ueMob = NodeList::GetNode(ueNodeId)->GetObject<MobilityModel>();
                Ptr<MobilityModel> gnbMob = gnbNode->GetObject<MobilityModel>();
                distance = ueMob->GetDistanceFrom(gnbMob);
                
                if (table_radio_5g.count(ueNodeId)) {
                    table_radio_5g[ueNodeId].servingGnb = gnbDev->GetCellId();
                }
                break; 
            }
        }

        if (distance >= 0) {
            std::cout << "Node " << ueNodeId << " | Dist: " << std::fixed << std::setprecision(1) 
                      << distance << " m | Serving Cell: " << servingCellId << std::endl;
            if (table_radio_5g.count(ueNodeId)) table_radio_5g[ueNodeId].distance = distance;
        } else {
            std::cout << "Node " << ueNodeId << " | Status: Searching for gNB (Cell " << servingCellId << ")..." << std::endl;
        }
    }
    Simulator::Schedule(Seconds(interval), &ComputeDistance, nrHelper, gnbNodes);
}


void ComputePacketLoss(Ptr<NrHelper> nrHelper) {
    double interval = 1.0; 
    Ptr<NrBearerStatsCalculator> bearerStats = nrHelper->GetRlcStatsCalculator();
    
    if (!bearerStats) {
        Simulator::Schedule(Seconds(interval), &ComputePacketLoss, nrHelper);
        return;
    }

    // Maps statiques pour stocker les valeurs précédentes (Delta)
    static std::map<uint64_t, uint64_t> lastDlTx, lastDlRx;
    static std::map<uint64_t, uint64_t> lastUlTx, lastUlRx;

    std::cout << "\n\033[1;31m--- 5G PACKET LOSS (%) ---\033[0m" << std::endl;

    for (uint32_t i = 0; i < 4; ++i) {
        uint64_t imsi = i + 3;
        uint8_t lcid = 3; // On se concentre sur le flux de données

        // --- Downlink ---
        uint64_t curDlTx = bearerStats->GetDlTxPackets(imsi, lcid);
        uint64_t curDlRx = bearerStats->GetDlRxPackets(imsi, lcid);
        uint64_t deltaDlTx = curDlTx - lastDlTx[imsi];
        uint64_t deltaDlRx = curDlRx - lastDlRx[imsi];
        
        double dlLossRate = 0.0;
        if (deltaDlTx > 0) {
            dlLossRate = (static_cast<double>(deltaDlTx - deltaDlRx) / deltaDlTx) * 100.0;
        }
        if (dlLossRate < 0) dlLossRate = 0; // Sécurité si Rx > Tx (rare en ns-3)

        // --- Uplink ---
        uint64_t curUlTx = bearerStats->GetUlTxPackets(imsi, lcid);
        uint64_t curUlRx = bearerStats->GetUlRxPackets(imsi, lcid);
        uint64_t deltaUlTx = curUlTx - lastUlTx[imsi];
        uint64_t deltaUlRx = curUlRx - lastUlRx[imsi];

        double ulLossRate = 0.0;
        if (deltaUlTx > 0) {
            ulLossRate = (static_cast<double>(deltaUlTx - deltaUlRx) / deltaUlTx) * 100.0;
        }

        // Sauvegarde pour le prochain intervalle
        lastDlTx[imsi] = curDlTx; lastDlRx[imsi] = curDlRx;
        lastUlTx[imsi] = curUlTx; lastUlRx[imsi] = curUlRx;

        uint32_t nodeId = i + 3;
        std::cout << "Node " << nodeId << " | DL Loss: " << std::fixed << std::setprecision(2) 
                  << dlLossRate << "% | UL Loss: " << ulLossRate << "%" << std::endl;

        // Mise à jour de la table pour le SnapshotManager
        if (table_radio_5g.count(nodeId)) {
            table_radio_5g[nodeId].packetLossDl = dlLossRate;
            table_radio_5g[nodeId].packetLossUl = ulLossRate;
        }
    }
    Simulator::Schedule(Seconds(interval), &ComputePacketLoss, nrHelper);
}
