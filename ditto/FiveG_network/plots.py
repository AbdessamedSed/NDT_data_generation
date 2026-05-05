import json
import os
import matplotlib.pyplot as plt
import time

INPUT_FILE = "comparison_live_report.json"
OUTPUT_DIR = "simulation_analysis"

# Métriques à traiter
NODE_METRICS = ['x', 'y', 'speed', 'sinr_dl', 'sinr_ul']
FLOW_METRICS = ['throughput']

def create_folders():
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
    for m in NODE_METRICS + FLOW_METRICS:
        path = os.path.join(OUTPUT_DIR, m)
        if not os.path.exists(path): os.makedirs(path)

def clean_id(val):
    if val is None: return "unknown"
    return str(val).replace("[", "").replace("]", "").split(":")[-1]

def process():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ Fichier {INPUT_FILE} introuvable.")
        return

    data = []
    try:
        with open(INPUT_FILE, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Erreur lors de la lecture du JSON : {e}")
        return

    if not data or not isinstance(data, list):
        print("❌ JSON vide ou format de liste incorrect.")
        return

    results = {}
    time_axis = []

    print(f"📊 Analyse de {len(data)} snapshots...")

    for entry in data:
        # Sécurité : on vérifie que l'entrée est bien un dictionnaire
        if not isinstance(entry, dict): continue
        
        t = entry.get('omnet_sim_time', 0)
        time_axis.append(t)
        
        # --- 1. TRAITEMENT DES NOEUDS ---
        pt_nodes = entry.get('data_omnet', [])
        dt_nodes = entry.get('data_ditto', [])
        
        # Sécurité : on s'assure que ce sont des listes
        if not isinstance(pt_nodes, list): pt_nodes = []
        if not isinstance(dt_nodes, list): dt_nodes = []

        for pt_n in pt_nodes:
            # CORRECTION : On vérifie que pt_n est un dictionnaire avant d'utiliser .get()
            if not isinstance(pt_n, dict): 
                continue 
            
            if pt_n.get('type') != 'ue': 
                continue

            ue_id = clean_id(pt_n.get('id'))
            if ue_id not in results:
                results[ue_id] = {m: {'pt': [], 'dt': []} for m in NODE_METRICS + FLOW_METRICS}

            # Trouver le noeud correspondant dans Ditto
            dt_n = None
            for n in dt_nodes:
                if isinstance(n, dict) and clean_id(n.get('id')) == ue_id:
                    dt_n = n
                    break

            for m in NODE_METRICS:
                results[ue_id][m]['pt'].append(pt_n.get(m, 0))
                results[ue_id][m]['dt'].append(dt_n.get(m, 0) if dt_n else 0)

        # --- 2. TRAITEMENT DES FLUX ---
        pt_flows = entry.get('flows_omnet', [])
        dt_flows = entry.get('flows_ditto', [])
        
        if not isinstance(pt_flows, list): pt_flows = []
        if not isinstance(dt_flows, list): dt_flows = []

        for pt_f in pt_flows:
            if not isinstance(pt_f, dict): continue
            
            dst = clean_id(pt_f.get('dst', ''))
            if dst in results:
                results[dst]['throughput']['pt'].append(pt_f.get('throughput', 0))
                
                # Trouver le flux correspondant dans Ditto
                dt_f = None
                for f in dt_flows:
                    if isinstance(f, dict) and clean_id(f.get('d')) == dst:
                        dt_f = f
                        break
                
                if dt_f:
                    val = dt_f.get('thr', dt_f.get('throughput'))
                    if val is None:
                        val = (dt_f.get('sz',0)*8)/dt_f.get('i',1) if dt_f.get('i',0)>0 else 0
                    results[dst]['throughput']['dt'].append(val)
                else:
                    results[dst]['throughput']['dt'].append(0)

    # --- 3. GÉNÉRATION DES GRAPHIQUES ---
    print(f"📈 Génération des graphiques dans {OUTPUT_DIR}...")
    for ue_id, metrics in results.items():
        for m_name, vals in metrics.items():
            if not vals['pt'] or len(vals['pt']) < 2: continue
            
            plt.figure(figsize=(10, 5))
            # Ajustement de la taille pour éviter les décalages si une liste est plus courte
            min_len = min(len(time_axis), len(vals['pt']), len(vals['dt']))
            
            plt.plot(time_axis[:min_len], vals['pt'][:min_len], label='OMNeT (Physical)', color='blue', linewidth=2)
            plt.plot(time_axis[:min_len], vals['dt'][:min_len], label='Ditto (Digital)', color='red', linestyle='--')
            plt.fill_between(time_axis[:min_len], vals['pt'][:min_len], vals['dt'][:min_len], color='gray', alpha=0.2)
            
            plt.title(f"{m_name.upper()} - {ue_id}")
            plt.xlabel("Simulation Time (s)")
            plt.ylabel(m_name)
            plt.legend()
            plt.grid(True, alpha=0.3)
            
            plt.savefig(os.path.join(OUTPUT_DIR, m_name, f"{ue_id}_{m_name}.png"))
            plt.close()
    print("✅ Terminé.")

if __name__ == "__main__":
    create_folders()
    process()