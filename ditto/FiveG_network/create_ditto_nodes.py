import requests
from requests.auth import HTTPBasicAuth

URL = "http://localhost:8080/api/2/things"
AUTH = HTTPBasicAuth("ditto", "ditto")
NS = "my5GNetwork"

data = {
    "nodes": [
      { "id": "ue0", "x": 0, "y": 0, "z": 0, "speed": 0, "serving_gnb": "nan", "sinr_dl": -999, "sinr_ul": -999, "sinr_d2d": -999 },
      { "id": "ue1", "x": 0, "y": 0, "z": 0, "speed": 0, "serving_gnb": "nan", "sinr_dl": -999, "sinr_ul": -999, "sinr_d2d": -999 },
      { "id": "ue2", "x": 0, "y": 0, "z": 0, "speed": 0, "serving_gnb": "nan", "sinr_dl": -999, "sinr_ul": -999, "sinr_d2d": -999 },
      { "id": "ue3", "x": 0, "y": 0, "z": 0, "speed": 0, "serving_gnb": "nan", "sinr_dl": -999, "sinr_ul": -999, "sinr_d2d": -999 },
      { "id": "gnb", "x": 0, "y": 0, "z": 0, "speed": 0, "serving_gnb": "unknown", "sinr_dl": -999, "sinr_ul": -999, "sinr_d2d": -999 }
    ],
    "flows": [
      { "type": "nan", "src": "server", "dst": "ue0", "packet_size": 0, "interval": 0 , "throughput": 0, "delay": 0 , "bler": 0 , "packet_loss": 0},
      { "type": "nan", "src": "server", "dst": "ue1", "packet_size": 0, "interval": 0, "throughput": 0 , "delay": 0, "bler": 0, "packet_loss": 0},
      { "type": "nan", "src": "server", "dst": "ue2", "packet_size": 0, "interval": 0, "throughput": 0 , "delay": 0, "bler": 0 , "packet_loss": 0},
      { "type": "nan", "src": "server", "dst": "ue3", "packet_size": 0, "interval": 0, "throughput": 0 ,"delay": 0, "bler": 0 , "packet_loss": 0}
    ]
}

# Création des Nodes
for node in data["nodes"]:
    t_id = f"{NS}:{node['id']}"
    # On balance tout le dictionnaire node directement dans attributes
    payload = {"attributes": node}
    res = requests.put(f"{URL}/{t_id}", json=payload, auth=AUTH)
    print(f"Node {t_id}: {res.status_code}")

# Création des Flows
for flow in data["flows"]:
    # Nettoyage rapide des noms et création ID
    src, dst = flow['src'].strip("[]"), flow['dst'].strip("[]")
    t_id = f"{NS}:{src}_to_{dst}"
    # Pareil, tout à plat dans attributes
    payload = {"attributes": flow}
    res = requests.put(f"{URL}/{t_id}", json=payload, auth=AUTH)
    print(f"Flow {t_id}: {res.status_code}")