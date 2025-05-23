from fastapi import FastAPI
from fastapi.responses import JSONResponse
import json, os

app = FastAPI(title="GNS3 Manager")

# Путь к папке с JSON-конфигурациями топологий
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOPOLOGY_DIR = os.path.join(BASE_DIR, "topologies")

@app.post("/select_topology")
def select_topology(data: dict):
    """
    Получает информацию о выбранной топологии от Experiment Controller.
    В реальной логике можно сохранить выбор, но здесь просто подтверждаем получение.
    """
    topology_name = data.get("name")
    print(f"Получен запрос на топологию: {topology_name}")
    return {"status": "topology selected", "topology": topology_name}

@app.get("/topologies/{name}")
def get_topology_config(name: str):
    """
    Возвращает JSON-конфигурацию топологии по имени (например, "torus").
    GNS3 VM Manager вызывает этот метод, чтобы получить описание топологии.
    """
    file_path = os.path.join(TOPOLOGY_DIR, f"{name}.json")
    if not os.path.isfile(file_path):
        return JSONResponse(status_code=404, content={"error": "Topology not found"})
    # Читаем JSON-файл топологии и возвращаем его содержимое
    with open(file_path, "r") as f:
        topology_data = json.load(f)
    return topology_data  # FastAPI автоматически преобразует dict в JSON
