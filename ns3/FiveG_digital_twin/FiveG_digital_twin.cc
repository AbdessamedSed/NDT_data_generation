#include <chrono>
#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/mobility-module.h"
#include "ns3/csma-module.h"
#include "ns3/tap-bridge-module.h"
#include "ns3/nr-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/netanim-module.h"
#include "ns3/applications-module.h"
#include "json/json.h"
#include <vector>
#include <iostream>
#include <fstream>
#include <sstream>
#include <map>
#include <algorithm>
#include <fstream>
#include <iomanip>
#include "ns3/nr-ue-rrc.h" 
#include "ns3/traffic-control-helper.h"
#include "ns3/traffic-control-layer.h"
#include "ns3/ipv4-interface.h"
#include "ns3/arp-cache.h"
#include "ns3/eps-bearer.h"
#include "ns3/nr-point-to-point-epc-helper.h"
#include "ns3/nr-eps-bearer.h"
#include "ns3/nr-epc-tft.h"
#include "debug-functions.h"
#include "metrics-calc.h"
#include "ns3/nr-ue-net-device.h"
#include "ns3/nr-ue-mac.h"
#include "ns3/nr-gnb-net-device.h"
#include "ns3/nr-gnb-mac.h"
#include "ns3/nr-bearer-stats-calculator.h"
#include "ns3/nr-common.h"
#include <set> 
#include <cctype> 
#include <curl/curl.h>


using namespace ns3;

// Latest PT simulation timestamp successfully applied in the DT.
static double g_lastPtSourceSimTime = -1.0;

// Latest PT timestamps independently applied for each synchronized domain.
static double g_lastPtSourceSimTimeM = -1.0;
static double g_lastPtSourceSimTimeT = -1.0;
using namespace ns3::nr;

NS_LOG_COMPONENT_DEFINE("Ditto5GControl");

// ===========================================================================
// GLOBAL DECLARATIONS
// =========================================================================== 

bool g_debugMode = false;   // this variable to enable or disbale the debugging functions



// void ComputeBler() {
//     double interval = 1.0;
//     std::cout << "\n\033[1;35m--- 5G RADIO HEALTH (BLER %) ---\033[0m" << std::endl;

//     for (uint32_t i = 0; i < 4; ++i) {
//         uint16_t rnti = i + 1; // Vérifie tes RNTI dans les logs
//         uint32_t nodeId = i + 3;

//         // --- Downlink ---
//         uint32_t dlTotal = g_dlAck[rnti] + g_dlNack[rnti];
//         double dlBler = (dlTotal > 0) ? (static_cast<double>(g_dlNack[rnti]) / dlTotal) * 100.0 : 0.0;

//         // --- Uplink ---
//         uint32_t ulTotal = g_ulAck[rnti] + g_ulNack[rnti];
//         double ulBler = (ulTotal > 0) ? (static_cast<double>(g_ulNack[rnti]) / ulTotal) * 100.0 : 0.0;

//         if (dlTotal > 0 || ulTotal > 0) {
//             std::cout << "Node " << nodeId << " | DL BLER: " << dlBler << "% (" << dlTotal << " pks)"
//                       << " | UL BLER: " << ulBler << "% (" << ulTotal << " pks)" << std::endl;
//         } else {
//             std::cout << "Node " << nodeId << " | Status: Idle (No radio traffic detected)" << std::endl;
//         }

//         if (table_radio_5g.count(nodeId)) {
//             table_radio_5g[nodeId].blerDl = dlBler;
//             table_radio_5g[nodeId].blerUl = ulBler;
//         }

//         // Reset
//         g_dlAck[rnti] = 0; g_dlNack[rnti] = 0;
//         g_ulAck[rnti] = 0; g_ulNack[rnti] = 0;
//     }
//     Simulator::Schedule(Seconds(interval), &ComputeBler);
// }


void PrintIncomingJson(std::string source, std::string jsonStr) {
    NS_LOG_INFO("\033[1;33m[DEBUG " << source << "]\033[0m Content: " << jsonStr);
    
    if (jsonStr.empty()) {
        NS_LOG_WARN("!!! WARNING: JSON received is EMPTY !!!");
    }
}


// ===========================================
//    This function for debugging
// ===========================================

void InstallControlTraffic(NodeContainer ueNodes, Ptr<Node> remoteHost, Ipv4Address remoteHostAddr) {
    uint16_t ulPort = 11000; // control port (différents de Ditto)
    uint16_t dlPort = 12000;

    for (uint32_t i = 0; i < ueNodes.GetN(); ++i) {
        Ptr<Node> ue = ueNodes.Get(i);
        Ipv4Address ueAddr = ue->GetObject<Ipv4>()->GetAddress(1, 0).GetLocal();

        // --- UPLINK CONTROL (UE -> Server) 
        UdpClientHelper ulClient(remoteHostAddr, ulPort + i);
        ulClient.SetAttribute("MaxPackets", UintegerValue(4294967295U));
        ulClient.SetAttribute("Interval", TimeValue(MilliSeconds(100))); 
        ulClient.SetAttribute("PacketSize", UintegerValue(1600));
        ApplicationContainer ulApp = ulClient.Install(ue);
        
        ulApp.Start(Seconds(1.0));
        ulApp.Get(0)->TraceConnectWithoutContext("Tx", MakeCallback(&TraceAppTx));


        UdpServerHelper ulServer(ulPort + i);
        ulServer.Install(remoteHost).Start(Seconds(1.0));

        // --- DOWNLINK CONTROL (Server -> UE)
        UdpClientHelper dlClient(ueAddr, dlPort + i);
        dlClient.SetAttribute("MaxPackets", UintegerValue(4294967295U));
        dlClient.SetAttribute("Interval", TimeValue(MilliSeconds(100)));
        dlClient.SetAttribute("PacketSize", UintegerValue(1600));
        ApplicationContainer dlApp = dlClient.Install(remoteHost);
        dlApp.Start(Seconds(1.0));

        UdpServerHelper dlServer(dlPort + i);
        dlServer.Install(ue).Start(Seconds(1.0));

        NS_LOG_INFO("Control traffic installed for UE " << i << " (UL Port: " << ulPort+i << ", DL Port: " << dlPort+i << ")");
    }
}


// ===========================================================================
// 1. DITTO DATA HANDLER
// ===========================================================================
class DittoDataHandler {
private:
    std::map<std::string, Ptr<Application>> m_flowApps;

    struct FlowConfig
    {
        int packetSize = 0;
        double interval = 0.0;
    };

    std::map<std::string, FlowConfig> m_lastFlowConfig;

public:
    void UpdateNodeMobility(std::string id, double x, double y, double z, double speed = 0.0) {
    std::string cleanId = id;

    cleanId.erase(std::remove(cleanId.begin(), cleanId.end(), '['), cleanId.end());
    cleanId.erase(std::remove(cleanId.begin(), cleanId.end(), ']'), cleanId.end());


    if (cleanId.find("my5GNetwork:") == std::string::npos && cleanId != "server") {
        cleanId = "my5GNetwork:" + cleanId;
    }


    // --- AJOUT DU DEBUG LOG ---
    if (thingIdToNode.count(cleanId)) {
        Ptr<Node> node = thingIdToNode[cleanId];
        uint32_t nodeId = node->GetId();
        Ptr<MobilityModel> mobility = node->GetObject<MobilityModel>();
        if (mobility) {
            mobility->SetPosition(Vector3D(x, y, z));
            table_radio_5g[nodeId].currentSpeed = speed;

            std::cout
                << "[NS3-MOBILITY] id=" << cleanId
                << " nodeId=" << nodeId
                << " x=" << x
                << " y=" << y
                << " z=" << z
                << " speed=" << speed
                << std::endl;
        }
    } else {
        std::cout
            << "[NS3-MOBILITY-ERROR] received=" << id
            << " mapped=" << cleanId
            << " not found in thingIdToNode"
            << std::endl;
    }
}

    Ipv4Address GetNodeIp(Ptr<Node> node) {
        Ptr<Ipv4> ipv4 = node->GetObject<Ipv4>();
        if (ipv4->GetNInterfaces() > 1) {
            // L'interface 0 est loopback, l'interface 1 est la 5G ou le P2P
            return ipv4->GetAddress(1, 0).GetLocal();
        }
        return Ipv4Address::GetAny();
    }

    void UpdateFlowParameters(std::string flowIdFromDitto, std::string srcStr, std::string dstStr, int pSize, double flowInt, double offeredRateBps) {
    // 1. Nettoyage et mapping des IDs Ditto vers ns-3
    auto clean = [](std::string n) {
        n.erase(std::remove(n.begin(), n.end(), '['), n.end());
        n.erase(std::remove(n.begin(), n.end(), ']'), n.end());
        if (n == "server") return std::string("my5GNetwork:remoteHost");
        return std::string("my5GNetwork:" + n);
    };

    std::string sId = clean(srcStr);
    // std::cout << "sId is  " << sId << std::endl;
    std::string dId = clean(dstStr);
    // std::cout << "dId is  " << dId << std::endl;
    
    // 2. Création d'un ID interne unique pour éviter de recréer le même flux
    std::string internalFlowId = sId + "->" + dId;

    // Ignore traffic updates when the synchronized parameters
    // have not changed.
    auto previous = m_lastFlowConfig.find(internalFlowId);

    if (
        previous != m_lastFlowConfig.end() &&
        previous->second.packetSize == pSize &&
        std::abs(previous->second.interval - flowInt) < 1e-12
    )
    {
        return;
    }

    m_lastFlowConfig[internalFlowId] = {
        pSize,
        flowInt
    };

    // Vérification de l'existence des noeuds
    if (thingIdToNode.count(sId) == 0 || thingIdToNode.count(dId) == 0) {
        // std::cout << "\033[1;31m[FLOW-ERROR]\033[0m Node not found: " << sId << " or " << dId << std::endl;
        return;
    }

    Ptr<Node> srcNode = thingIdToNode[sId];
    Ptr<Node> dstNode = thingIdToNode[dId];

    // 3. MISE À JOUR si le flux existe déjà
    if (m_flowApps.count(internalFlowId)) {
        Ptr<Application> app = m_flowApps[internalFlowId];
        app->SetAttribute("Interval", TimeValue(Seconds(flowInt)));
        app->SetAttribute("PacketSize", UintegerValue(pSize));
        
        // Mise à jour des infos pour le SnapshotManager
        active_flows[internalFlowId].packetSize = pSize;
        active_flows[internalFlowId].interval = flowInt;
        active_flows[internalFlowId].offeredRateBps = offeredRateBps;
        
        // std::cout << "\033[1;34m[FLOW-UPDATE]\033[0m " << internalFlowId << " | Int: " << flowInt << "s" << std::endl;
    }
    // 4. INSTALLATION si c'est un nouveau flux
    else {
        // std::cout << "\033[1;32m[FLOW-INSTALL]\033[0m " << sId << " to " << dId << std::endl;

        // Attribution d'un port unique (commence à 9000)
        uint16_t port = 9000 + m_flowApps.size();

        // Installation du Serveur sur la destination
        UdpServerHelper serverHelper(port);
        ApplicationContainer serverApp = serverHelper.Install(dstNode);
        serverApp.Start(Seconds(0.01));

        // Récupération de l'IP de destination (Interface 1 = 5G ou P2P)
        Ipv4Address destIp = dstNode->GetObject<Ipv4>()->GetAddress(1, 0).GetLocal();
        // std::cout << "\n adresse de la destination est : " << destIp << std::endl;

        // Installation du Client sur la source
        UdpClientHelper clientHelper(destIp, port);
        clientHelper.SetAttribute("MaxPackets", UintegerValue(4294967295U));
        clientHelper.SetAttribute("Interval", TimeValue(Seconds(flowInt)));
        clientHelper.SetAttribute("PacketSize", UintegerValue(pSize));

        ApplicationContainer clientApps = clientHelper.Install(srcNode);
        Ptr<Application> clientPtr = clientApps.Get(0);
        
        // Démarrage immédiat (Now + 10ms)
        clientApps.Start(Seconds(Simulator::Now().GetSeconds() + 1.0));

        // Sauvegarde dans les maps globales
        m_flowApps[internalFlowId] = clientPtr;
        
        FlowInfo info;
        info.flowId = internalFlowId;
        info.srcName = srcStr;
        info.dstName = dstStr;
        info.packetSize = pSize;
        info.interval = flowInt;
        info.srcNode = srcNode;
        info.dstNode = dstNode;
        info.offeredRateBps = offeredRateBps;
        active_flows[internalFlowId] = info;
    }
}

};


DittoDataHandler g_handler; 

// ===========================================================================
// 2. DITTO LOGGER
// ===========================================================================
class DittoLogger {
public:
    void Open(std::string filename) {
        m_file.open(filename, std::ios::out | std::ios::trunc);
        m_file << "[\n";
        m_first = true;
    }
    void LogSnapshot(const Json::Value& root) {
        if (!m_file.is_open()) return;
        if (!m_first) m_file << ",\n";
        Json::StreamWriterBuilder builder;
        builder["indentation"] = "  ";
        m_file << Json::writeString(builder, root);
        m_first = false;
        m_file.flush();
    }
    void Close() {
        if (m_file.is_open()) { m_file << "\n]"; m_file.close(); }
    }
private:
    std::ofstream m_file;
    bool m_first;
};

size_t WriteCallback(void* contents, size_t size, size_t nmemb, void* userp) {
    ((std::string*)userp)->append((char*)contents, size * nmemb);
    return size * nmemb;
}

// ===========================================================================
// 3. DITTO CONTROLLER APPLICATION (UDP Signal + RAM Buffer)
// ===========================================================================
class DittoControllerApp : public Application {
public:
    DittoControllerApp() : m_port(5000) {}
    
    // Setup reste identique
    void Setup(uint16_t port, std::string logFile) { 
        m_port = port; 
        m_logFileName = logFile;
    }

private:
    uint16_t m_port;
    Ptr<Socket> m_socket;
    std::string m_logFileName;

    struct SnapshotBuffer
    {
        uint32_t chunkCount = 0;
        std::vector<std::string> chunks;
        std::vector<bool> received;
        double lastUpdate = 0.0;
    };

    std::map<std::string, SnapshotBuffer> m_snapshots;

    static constexpr double REASSEMBLY_TIMEOUT_S = 2.0;
    // std::string m_bufferPath = "/dev/shm/ditto_buffer.json"; 
    
    DittoLogger m_logger;       

    virtual void StartApplication() override {
        m_logger.Open(m_logFileName);

        m_socket = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
        m_socket->Bind(InetSocketAddress(Ipv4Address::GetAny(), m_port));
        m_socket->SetRecvCallback(MakeCallback(&DittoControllerApp::HandleRead, this));
        
       NS_LOG_INFO("[NS3] Ready. Waiting for UDP signals on port " << m_port << "...");
    }

    virtual void StopApplication() override {
        m_logger.Close();
        if (m_socket) m_socket->Close();
    }

    // MODIFICATION ICI : On lit le paquet, pas le fichier
    void CleanupExpiredSnapshots()
    {
        const double now = Simulator::Now().GetSeconds();

        for (auto it = m_snapshots.begin(); it != m_snapshots.end(); )
        {
            if ((now - it->second.lastUpdate) > REASSEMBLY_TIMEOUT_S)
            {
                NS_LOG_WARN(
                    "[NS3] Dropping incomplete snapshot "
                    << it->first
                    << " after reassembly timeout"
                );

                it = m_snapshots.erase(it);
            }
            else
            {
                ++it;
            }
        }
    }

    void HandleRead(Ptr<Socket> socket)
    {
        Ptr<Packet> packet;
        Address from;

        while ((packet = socket->RecvFrom(from)))
        {
            const uint32_t dataSize = packet->GetSize();

            std::vector<uint8_t> buffer(dataSize);
            packet->CopyData(
                buffer.data(),
                dataSize
            );

            std::string message(
                reinterpret_cast<char*>(buffer.data()),
                dataSize
            );

            if (message.empty())
            {
                continue;
            }

            // Expected format:
            // NDT1|snapshot_id|chunk_index|chunk_count|sim_time|payload
            if (message.rfind("NDT1|", 0) != 0)
            {
                NS_LOG_WARN(
                    "[NS3] Ignoring non-NDT1 control message"
                );
                continue;
            }

            size_t p1 = message.find('|', 5);
            size_t p2 = (p1 == std::string::npos)
                ? std::string::npos
                : message.find('|', p1 + 1);
            size_t p3 = (p2 == std::string::npos)
                ? std::string::npos
                : message.find('|', p2 + 1);
            size_t p4 = (p3 == std::string::npos)
                ? std::string::npos
                : message.find('|', p3 + 1);

            if (
                p1 == std::string::npos ||
                p2 == std::string::npos ||
                p3 == std::string::npos ||
                p4 == std::string::npos
            )
            {
                NS_LOG_WARN(
                    "[NS3] Malformed NDT1 chunk header"
                );
                continue;
            }

            const std::string snapshotId =
                message.substr(5, p1 - 5);

            const uint32_t chunkIndex =
                static_cast<uint32_t>(
                    std::stoul(
                        message.substr(
                            p1 + 1,
                            p2 - p1 - 1
                        )
                    )
                );

            const uint32_t chunkCount =
                static_cast<uint32_t>(
                    std::stoul(
                        message.substr(
                            p2 + 1,
                            p3 - p2 - 1
                        )
                    )
                );

            const std::string simTimeField =
                message.substr(
                    p3 + 1,
                    p4 - p3 - 1
                );

            const std::string chunkPayload =
                message.substr(p4 + 1);

            if (
                chunkCount == 0 ||
                chunkIndex >= chunkCount
            )
            {
                NS_LOG_WARN(
                    "[NS3] Invalid chunk metadata for snapshot "
                    << snapshotId
                );
                continue;
            }

            SnapshotBuffer& state =
                m_snapshots[snapshotId];

            if (
                state.chunkCount == 0 ||
                state.chunkCount != chunkCount
            )
            {
                state.chunkCount = chunkCount;
                state.chunks.assign(
                    chunkCount,
                    std::string()
                );
                state.received.assign(
                    chunkCount,
                    false
                );
            }

            state.lastUpdate =
                Simulator::Now().GetSeconds();

            // Duplicate chunks are harmless.
            if (!state.received[chunkIndex])
            {
                state.chunks[chunkIndex] =
                    chunkPayload;

                state.received[chunkIndex] =
                    true;
            }

            uint32_t receivedCount = 0;

            for (bool received : state.received)
            {
                if (received)
                {
                    ++receivedCount;
                }
            }

            // Verbose chunk trace disabled for dataset generation.
            /*
            std::cout
                << "[NS3-CHUNK] snapshot=" << snapshotId
                << " chunk=" << (chunkIndex + 1)
                << "/" << chunkCount
                << " bytes=" << chunkPayload.size()
                << std::endl;
            */

            if (receivedCount == chunkCount)
            {
                std::string fullJson;

                size_t totalSize = 0;
                for (const auto& chunk : state.chunks)
                {
                    totalSize += chunk.size();
                }

                fullJson.reserve(totalSize);

                for (const auto& chunk : state.chunks)
                {
                    fullJson += chunk;
                }

                // Verbose reassembly trace disabled for dataset generation.
                /*
                std::cout
                    << "[NS3-REASSEMBLY] snapshot=" << snapshotId
                    << " complete bytes=" << fullJson.size()
                    << std::endl;
                */

                m_snapshots.erase(snapshotId);

                ProcessJson(fullJson);
            }
        }

        CleanupExpiredSnapshots();
    }

    void ProcessJson(std::string jsonStr) {
    Json::Value root;
    Json::CharReaderBuilder builder;
    std::string errors;
    std::unique_ptr<Json::CharReader> reader(builder.newCharReader());

    if (!reader->parse(jsonStr.c_str(), jsonStr.c_str() + jsonStr.size(), &root, &errors)) return;

    // Track independently which PT domains were refreshed by this update.
    if (root.isObject() && root.isMember("t")) {
        const double sourceTime = root["t"].asDouble();

        const bool refreshMobility =
            root.isMember("n") &&
            root["n"].isArray() &&
            !root["n"].empty();

        const bool refreshTraffic =
            root.isMember("f") &&
            root["f"].isArray() &&
            !root["f"].empty();

        if (refreshMobility) {
            g_lastPtSourceSimTimeM = sourceTime;
        }

        if (refreshTraffic) {
            g_lastPtSourceSimTimeT = sourceTime;
        }

        // Retained for backward-compatible global diagnostics.
        g_lastPtSourceSimTime = sourceTime;
    }

    // --- CAS 1 : C'est un OBJET {"n": ..., "f": ...} ---
    if (root.isObject()) {
        // Sécurité : on vérifie isObject() AVANT isMember()
        if (root.isMember("n") && root["n"].isArray()) {
            for (const auto& node : root["n"]) {
                g_handler.UpdateNodeMobility(node["id"].asString(),
                                            node["x"].asDouble(),
                                            node["y"].asDouble(),
                                            node.get("z", 0.0).asDouble(),
                                            node.get("speed", 0.0).asDouble());
            }
        }
        if (root.isMember("f") && root["f"].isArray()) {
            for (const auto& flow : root["f"]) {
                std::string sId = flow["s"].asString();
                std::string dId = flow["d"].asString();
                int pSize = flow.get("sz", 1450).asInt();
                double flowInt = flow.get("i", 0.001).asDouble();

                double offeredRateBps = (pSize * 8.0) / flowInt;

                // std::cout << "\n Thr is : " << thrTheoNs3 << std::endl;


                g_handler.UpdateFlowParameters("sync_flow", sId, dId, pSize, flowInt, offeredRateBps);

                
            }
        }
    }
    // --- CAS 2 : C'est une LISTE (Format Scapy / Ditto Search) ---
    else if (root.isArray()) {
        for (const auto& item : root) {
            if (!item.isMember("thingId") || !item.isMember("attributes")) continue;
            
            std::string tid = item["thingId"].asString();
            const Json::Value& attr = item["attributes"];

            // Si c'est un UE ou gNB (contient x, y, z)
            if (attr.isMember("x")) {
                g_handler.UpdateNodeMobility(tid, 
                                            attr["x"].asDouble(), 
                                            attr["y"].asDouble(), 
                                            attr.get("z", 0.0).asDouble(), 
                                            attr.get("speed", 0.0).asDouble());
            }
            // Si c'est un Flow (contient s et d ou src et dst)

            else if (attr.isMember("s") && attr.isMember("d")) {

                std::string sId = attr["s"].asString();
                std::string dId = attr["d"].asString();
                int pSize = attr.get("sz", 1450).asInt();
                double flowInt = attr.get("i", 0.001).asDouble();

                double offeredRateBps = (pSize * 8.0) / flowInt;

                g_handler.UpdateFlowParameters("sync_flow", sId, dId, pSize, flowInt, offeredRateBps);
            }
        }
    }
}
};


class SnapshotManager {
private:
    std::fstream m_file;
    bool m_isFirst = true;

public:
    void Open(std::string filename) {
        // On ouvre en lecture/écriture
        m_file.open(filename, std::ios::out | std::ios::trunc);
        m_file << "[\n";
    
        m_file.flush();
    }

    void DoSnapshot() {
        if (!m_file.is_open()) return;

        double now = Simulator::Now().GetSeconds();

        // Si c'est pas le premier, on recule pour effacer le "]" et mettre une virgule
        if (!m_isFirst) {
            m_file.seekp(-2, std::ios::end); 
            m_file << ",\n";
        }
        m_isFirst = false;

        m_file << "  {\n";
        m_file << "    \"timestamp\": " << std::fixed << std::setprecision(2) << now << ",\n";

        const double snapshotWallTime =
            std::chrono::duration<double>(
                std::chrono::system_clock::now().time_since_epoch()
            ).count();

        m_file << "    \"wall_time\": "
               << std::fixed << std::setprecision(6)
               << snapshotWallTime << ",\n";
        m_file << "    \"source_sim_time\": "
               << std::fixed << std::setprecision(3)
               << g_lastPtSourceSimTime << ",\n";

        m_file << "    \"source_sim_time_M\": "
               << std::fixed << std::setprecision(3)
               << g_lastPtSourceSimTimeM << ",\n";

        m_file << "    \"source_sim_time_T\": "
               << std::fixed << std::setprecision(3)
               << g_lastPtSourceSimTimeT << ",\n";

        // --- SECTION NODES (UEs et gNBs) ---
        m_file << "    \"nodes\": [\n";
        bool firstNode = true;
        for (auto const& [dittoId, nodePtr] : thingIdToNode) {
            uint32_t nid = nodePtr->GetId();
            // On filtre pour ne prendre que les équipements physiques
            if (dittoId.find("ue") != std::string::npos || dittoId.find("gnb") != std::string::npos) {
                if (!firstNode) m_file << ",\n";
                
                Ptr<MobilityModel> mob = nodePtr->GetObject<MobilityModel>();
                Vector pos = mob->GetPosition();
                UeRadioTable& radio = table_radio_5g[nid];

                m_file << "      { ";
                m_file << "\"id\": \"" << dittoId << "\", ";
                m_file << "\"x\": " << pos.x << ", \"y\": " << pos.y << ", \"z\": " << pos.z << ", ";
                m_file << "\"speed\": " << radio.currentSpeed << ", ";
                
                if (dittoId.find("ue") != std::string::npos) {
                    m_file << "\"serving_gnb\": \"" << radio.servingGnb << "\", ";
                    m_file << "\"sinr_dl\": " << radio.dlSinr ;
                    // m_file << "\"sinr_d2d\": -999";
                } else {
                    m_file << "\"type\": \"gNB\"";
                }
                m_file << " }";
                firstNode = false;
            }
        }
        m_file << "\n    ],\n";

        // --- SECTION FLOWS ---
        m_file << "    \"flows\": [\n";
        bool firstFlow = true;
        for (auto const& [fid, flow] : active_flows) {
            if (!firstFlow) m_file << ",\n";
            
            bool isDl = (flow.srcName.find("server") != std::string::npos);
            uint32_t ueId = isDl ? flow.dstNode->GetId() : flow.srcNode->GetId();
            UeRadioTable& stats = table_radio_5g[ueId];

            m_file << "      { ";
            m_file << "\"type\": \"" << (isDl ? "DL" : "UL") << "\", ";
            m_file << "\"src\": \"" << flow.srcName << "\", ";
            m_file << "\"dst\": \"" << flow.dstName << "\", ";
            // m_file << "\"app\": \"" << (isDl ? "DL_Traffic" : "UL_Traffic") << "\", ";
            m_file << "\"packet_size\": " << flow.packetSize << ", ";
            m_file << "\"interval\": " << std::setprecision(9) << flow.interval << ", ";
            m_file << "\"offered_rate_bps\": " << std::setprecision(6) << flow.offeredRateBps << ", "; m_file << "\"rlc_throughput_Bps\": " << std::setprecision(6) << stats.rlcThroughputDl;
            // m_file << "\"delay\": " << (isDl ? stats.macDelayDl : stats.macDelayUl) << ", ";
            // m_file << "\"bler\": " << (isDl ? stats.blerDl : stats.blerUl) << ", ";
            // m_file << "\"packet_loss\": " << (isDl ? stats.packetLossDl : stats.packetLossUl);
            m_file << " }";
            firstFlow = false;
        }
        m_file << "\n    ]\n";
        
        // --- FERMETURE DU SNAPSHOT ---
        m_file << "  }\n]"; // 
        m_file.flush();

        Simulator::Schedule(Seconds(g_snapshotInterval), &SnapshotManager::DoSnapshot, this);

    }

    void Close() {
        if (m_file.is_open()) m_file.close();
    }
};


SnapshotManager g_snapshotMgr;


/**
 * Reads the initial JSON configuration and prints exactly what it finds.
 * Uses std::set to ensure each UE/gNB is only counted ONCE.
 */
void PreParseInitialEntities(std::string filePath, std::vector<std::string>& ueList, std::vector<std::string>& gnbList) {
    std::ifstream ifs(filePath);
    if (!ifs.is_open()) {
        // std::cout << "\033[1;31m[PRE-PARSE] ERROR: Could not open " << filePath << "\033[0m" << std::endl;
        return;
    }

    Json::Value root;
    Json::CharReaderBuilder builder;
    std::string errors;
    
    std::set<std::string> uniqueUes;
    std::set<std::string> uniqueGnbs;

    if (Json::parseFromStream(builder, ifs, &root, &errors)) {
        if (root.isArray()) {
            // std::cout << "\033[1;34m[PRE-PARSE] Starting Strict JSON scan...\033[0m" << std::endl;
            
            for (const auto& item : root) {
                if (!item.isMember("thingId")) continue;
                
                std::string tid = item["thingId"].asString();

                // --- 1. STRICT UE FILTER ---
                // Must start with "my5GNetwork:ue"
                // Must NOT contain "_to_" (this filters out flows like server_to_ue)
                if (tid.find("my5GNetwork:ue") == 0 && tid.find("_to_") == std::string::npos) {
                    
                    // Verify that what follows "ue" is actually a number (to avoid "ue_template" etc)
                    // "my5GNetwork:ue" is 14 characters long
                    if (tid.length() > 14 && std::isdigit(tid[14])) {
                        if (uniqueUes.find(tid) == uniqueUes.end()) {
                            uniqueUes.insert(tid);
                            // std::cout << "  [NODE] Found Physical UE: " << tid << std::endl;
                        }
                    }
                } 
                // --- 2. STRICT GNB FILTER ---
                // Must start with "my5GNetwork:gnb"
                else if (tid.find("my5GNetwork:gnb") == 0 && tid.find("_to_") == std::string::npos) {
                    if (uniqueGnbs.find(tid) == uniqueGnbs.end()) {
                        uniqueGnbs.insert(tid);
                        // std::cout << "  [NODE] Found Physical gNB: " << tid << std::endl;
                    }
                }
                else {
                    // This is likely a flow or a remote host, we ignore it for Node Creation
                    // std::cout << "  [IGNORE] Skipping Flow/Object: " << tid << std::endl;
                }
            }
        }
    }
    ifs.close();

    ueList.assign(uniqueUes.begin(), uniqueUes.end());
    gnbList.assign(uniqueGnbs.begin(), uniqueGnbs.end());

    // std::cout << "\033[1;32m[PRE-PARSE] SUCCESS: " << ueList.size() 
    //           << " unique UE nodes and " << gnbList.size() << " gNB nodes identified.\033[0m" << std::endl;
}


// ===========================================================================
// 4. MAIN
// ===========================================================================
int main(int argc, char *argv[]) {
    // Simulation duration can be selected from the launcher.
    double simTime = 1200.0;

    // --- 1. EXPLICIT DIGITAL-TWIN TOPOLOGY ---
    //
    // Static topology is configured when ns-3 starts.
    // Ditto remains responsible only for dynamic state synchronization.
    uint32_t nUes = 10;
    uint32_t nGnbs = 1;

    CommandLine cmd(__FILE__);
    cmd.AddValue(
        "numUes",
        "Number of UE nodes in the digital twin",
        nUes
    );
    cmd.AddValue(
        "numGnbs",
        "Number of gNB nodes in the digital twin",
        nGnbs
    );
        cmd.AddValue(
        "simTime",
        "Simulation duration in seconds",
        simTime
    );
cmd.Parse(argc, argv);

    std::vector<std::string> discoveredUes;
    std::vector<std::string> discoveredGnbs;

    for (uint32_t i = 0; i < nUes; ++i)
    {
        discoveredUes.push_back(
            "my5GNetwork:ue" + std::to_string(i)
        );
    }

    if (nGnbs == 1)
    {
        // Current OMNeT/Ditto identifier.
        discoveredGnbs.push_back(
            "my5GNetwork:gnb0"
        );
    }
    else
    {
        for (uint32_t i = 0; i < nGnbs; ++i)
        {
            discoveredGnbs.push_back(
                "my5GNetwork:gnb" + std::to_string(i)
            );
        }
    }

    NS_LOG_INFO(
        "[NS3] Topology configured: "
        << nUes << " UE(s), "
        << nGnbs << " gNB(s)"
    );

    GlobalValue::Bind ("SimulatorImplementationType", StringValue ("ns3::RealtimeSimulatorImpl"));

    // --- 2. NODE CREATION ---
    NodeContainer tapNodes, gnbNodes, ueNodes, remoteHost;
    tapNodes.Create(2); 
    gnbNodes.Create(nGnbs); 
    ueNodes.Create(nUes); 
    remoteHost.Create(1);

    // --- 3. MOBILITY SETUP ---
    MobilityHelper mobility;
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.Install(tapNodes);
    mobility.Install(gnbNodes);
    mobility.Install(ueNodes); 
    mobility.Install(remoteHost);

    // Positions initiales dynamiques
    // for (uint32_t i = 0; i < nGnbs; ++i) {
    //     gnbNodes.Get(i)->GetObject<MobilityModel>()->SetPosition(Vector(726.0 + (i * 100), 277.0, 0.0));
    // }
    // for (uint32_t i = 0; i < nUes; ++i) {
    //     ueNodes.Get(i)->GetObject<MobilityModel>()->SetPosition(Vector(510.0 + i, 510.0, 0.0));
    // }

    // --- 4. DITTO MAPPING ---
    for (uint32_t i = 0; i < nGnbs; ++i) thingIdToNode[discoveredGnbs[i]] = gnbNodes.Get(i);
    for (uint32_t i = 0; i < nUes; ++i) thingIdToNode[discoveredUes[i]] = ueNodes.Get(i);
    thingIdToNode["my5GNetwork:remoteHost"] = remoteHost.Get(0);

    // --- 5. CONTROL NETWORK (TAP Bridge & Ditto App) ---
    InternetStackHelper internetControl;
    internetControl.Install(tapNodes);

    CsmaHelper csma;
    csma.SetChannelAttribute("DataRate", StringValue("100Mbps"));
    csma.SetChannelAttribute("Delay", StringValue("1ms"));
    NetDeviceContainer csmaDevs = csma.Install(tapNodes);

    Ipv4AddressHelper ipv4Control;
    ipv4Control.SetBase("10.1.1.0", "255.255.255.0");
    Ipv4InterfaceContainer csmaIfaces = ipv4Control.Assign(csmaDevs);

    TapBridgeHelper tapBridge;
    tapBridge.SetAttribute("Mode", StringValue("UseLocal"));
    tapBridge.SetAttribute("DeviceName", StringValue("thetap"));
    tapBridge.Install(tapNodes.Get(0), csmaDevs.Get(0));

    Ptr<DittoControllerApp> dittoApp = CreateObject<DittoControllerApp>();
    dittoApp->Setup(5000, "ns3_received_history.json");
    tapNodes.Get(1)->AddApplication(dittoApp);
    dittoApp->SetStartTime(Seconds(0.1));


    /*
        nouveau bloc de config
    */

    Ptr<NrPointToPointEpcHelper> epcHelper = CreateObject<NrPointToPointEpcHelper>();
    Ptr<NrHelper> nrHelper = CreateObject<NrHelper>();

    // nrHelper->SetGnbAntennaAttribute("AntennaType", StringValue("ns3::IsotropicAntennaModel"));
    // nrHelper->SetUeAntennaAttribute("AntennaType", StringValue("ns3::IsotropicAntennaModel"));
    nrHelper->SetEpcHelper(epcHelper);

    // nrHelper->SetSpectrumPropagationLossModelAttribute("Scenario", StringValue("UMa"));


    nrHelper->SetGnbPhyAttribute("TxPower", DoubleValue(20.0));
    // nrHelper->SetUePhyAttribute("TxPower", DoubleValue(26.0));


    nrHelper->SetUePhyAttribute("NoiseFigure", DoubleValue(5.0)); 
    nrHelper->SetGnbPhyAttribute("NoiseFigure", DoubleValue(5.0));

    // Beamforming
    // Ptr<IdealBeamformingHelper> bfHelper = CreateObject<IdealBeamformingHelper>();
    // bfHelper->SetAttribute("BeamformingPeriodicity", TimeValue(MilliSeconds(1000)));

    // nrHelper->SetBeamformingHelper(bfHelper);



    // Spectre et Bande passante (3.5 GHz, 100 MHz)
    CcBwpCreator ccBwpCreator;
    CcBwpCreator::SimpleOperationBandConf bandConf(3.5e9, 18e6, 1);
    OperationBandInfo band = ccBwpCreator.CreateOperationBandContiguousCc(bandConf);
    Ptr<NrChannelHelper> channelHelper = CreateObject<NrChannelHelper>();
    channelHelper->ConfigureFactories("UMa", "Default", "ThreeGpp");

    channelHelper->SetAttribute("Scenario", StringValue("UMa"));

    channelHelper->AssignChannelsToBands({band});

    // Installation des couches Internet (GNB, UE, RemoteHost)
    InternetStackHelper internet5G;
    internet5G.Install(gnbNodes); 
    internet5G.Install(ueNodes); 
    internet5G.Install(remoteHost);

    // Installation des terminaux 5G
    NetDeviceContainer gnbDevs = nrHelper->InstallGnbDevice(gnbNodes, CcBwpCreator::GetAllBwps({band}));
    NetDeviceContainer ueDevs = nrHelper->InstallUeDevice(ueNodes, CcBwpCreator::GetAllBwps({band}));
    
    // IP et Attachement
    epcHelper->AssignUeIpv4Address(NetDeviceContainer(ueDevs));
    nrHelper->AttachToClosestGnb(ueDevs, gnbDevs);

    // --- 7. BEARER ACTIVATION (Une seule boucle propre) ---
    for (uint32_t i = 0; i < ueDevs.GetN(); ++i) {
        Ptr<NrUeNetDevice> nrUeDev = ueDevs.Get(i)->GetObject<NrUeNetDevice>();
        uint64_t imsi = nrUeDev->GetImsi();
        epcHelper->ActivateEpsBearer(ueDevs.Get(i), imsi, Create<NrEpcTft>(), 
                                    NrEpsBearer(NrEpsBearer::NGBR_VIDEO_TCP_DEFAULT));
    }

    // --- 8. METRICS & TRACES (Connexion finale) ---
    ConnectSimulationTraces(ueDevs, gnbDevs, ueNodes);
    
    Simulator::Schedule(Seconds(2), &ComputeThroughput, nrHelper, ueDevs);
    // Simulator::Schedule(Seconds(1.2), &ComputeLatency, nrHelper, nGnbs, nUes);
    Simulator::Schedule(Seconds(3), &ComputeDistance, nrHelper, gnbNodes, nGnbs, nUes);
    // Simulator::Schedule(Seconds(1.4), &ComputePacketLoss, nrHelper, nGnbs, nUes);
    // Simulator::Schedule(Seconds(1.5), &ComputeBler, nrHelper, nGnbs, nUes);

    // --- 9. CORE NETWORK & INTERNET ROUTING ---
    Ptr<Node> pgw = epcHelper->GetPgwNode();
    PointToPointHelper p2p;
    p2p.SetDeviceAttribute("DataRate", StringValue("10Gbps"));
    p2p.SetChannelAttribute("Delay", StringValue("1ms"));
    NetDeviceContainer internetDevices = p2p.Install(pgw, remoteHost.Get(0));
    
    Ipv4AddressHelper ipv4Internet;
    ipv4Internet.SetBase("1.0.0.0", "255.0.0.0");
    Ipv4InterfaceContainer internetIpIfaces = ipv4Internet.Assign(internetDevices);

    // Routage statique pour le RemoteHost
    Ipv4StaticRoutingHelper ipv4RoutingHelper;
    Ptr<Ipv4StaticRouting> remoteHostStaticRouting = ipv4RoutingHelper.GetStaticRouting(remoteHost.Get(0)->GetObject<Ipv4>());
    remoteHostStaticRouting->AddNetworkRouteTo(Ipv4Address("7.0.0.0"), Ipv4Mask("255.0.0.0"), Ipv4Address("1.0.0.1"), 1);
    
    // Routage par défaut pour les UEs
    Ipv4StaticRoutingHelper staticRouting;
    for (uint32_t i = 0; i < ueNodes.GetN(); ++i) {
        Ptr<Ipv4StaticRouting> ueStaticRouting = staticRouting.GetStaticRouting(ueNodes.Get(i)->GetObject<Ipv4>());
        ueStaticRouting->SetDefaultRoute(Ipv4Address("7.0.0.1"), 1);
    }
    
    // --- 10. FINALIZATION & RUN ---
    // Fix mobilité pour tous les noeuds
    for (uint32_t i = 0; i < NodeList::GetNNodes(); ++i) {
        Ptr<Node> n = NodeList::GetNode(i);
        if (!n->GetObject<MobilityModel>()) mobility.Install(n);
    }


    // if (g_debugMode) {
    //     Simulator::Schedule(Seconds(1.0), &CheckInterfaceStatus, ueNodes.Get(0));
    //     Simulator::Schedule(Seconds(5.0), &CheckInterfaceStatus, ueNodes.Get(0));
    //     Simulator::Schedule(Seconds(10.0), &CheckInterfaceStatus, ueNodes.Get(0));
    //     Simulator::Schedule(Seconds(1.0), &CheckNeighborCache, ueNodes.Get(0));
    //     Simulator::Schedule(Seconds(5.0), &CheckNeighborCache, ueNodes.Get(0));
    //     Simulator::Schedule(Seconds(10.0), &CheckNeighborCache, ueNodes.Get(0));
    // }

    nrHelper->EnableTraces();
    g_snapshotMgr.Open(g_outputFile);
    Simulator::Schedule(Seconds(g_snapshotInterval), &SnapshotManager::DoSnapshot, &g_snapshotMgr);

    std::cout << "NS3_READY_FOR_DATA" << std::endl; // Le signal magique
    NS_LOG_INFO("Simulation Starting...");
    Simulator::Stop(Seconds(simTime));
    Simulator::Run();

    g_snapshotMgr.Close();
    Simulator::Destroy();
    return 0;
}

