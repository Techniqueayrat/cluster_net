from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import requests, subprocess, time, asyncio
from .utils_ssh import push_openmpi_files_all, run_mpi

app = FastAPI(title="Experiment Controller")
EXPCTL_REST = "http://localhost:8000" 
GNS3_SERVER_URL = "http://localhost:3080"
GNS3_TOKEN = None  # Токен авторизации GNS3 server будет сохранен здесь
gns3_proc: subprocess.Popen | None = None
PLACEMENT_URL = "http://localhost:8003/map"
METRICS_URL   = "http://localhost:8004"
experiment_counter = 0  # простой счётчик для ID экспериментов
experiments = {}  # хранение информации об экспериментах в памяти (можно сохранять в JSON при необходимости)

# Список активных WebSocket-соединений для отправки статусов GUI
active_connections: list[WebSocket] = []  

class ExperimentRequest(BaseModel):
    topology: str
    task_topology: str = "STAR"
    strategy: str = "Simple"

@app.on_event("startup")
def startup_event():
    """Запускается при старте FastAPI-приложения."""
    global GNS3_TOKEN, gns3_proc
    # 1. Запуск локального сервера gns3server как отдельного процесса
    gns3_proc = subprocess.Popen(["gns3server"])
    # Небольшая пауза, чтобы gns3server успел запуститься
    time.sleep(3)
    # 2. Авторизация на gns3server через REST API (username=admin, password=admin)
    resp = requests.post(f"{GNS3_SERVER_URL}/v3/access/users/login",
                         data={"username": "admin", "password": "admin"})
    # Извлекаем токен доступа для последующего использования
    GNS3_TOKEN = resp.json().get("access_token")
    print("GNS3 Server authenticated, token:", GNS3_TOKEN)

@app.post("/experiments/start")
async def start_experiment(req: ExperimentRequest):
    """
    REST-метод для запуска нового эксперимента.
    Клиент (GUI) вызывает этот метод, передавая название топологии (например, "torus").
    """
    topology = req.topology
    task_topology = req.task_topology
    strategy = req.strategy
    global experiment_counter
    exp_id = experiment_counter
    experiment_counter += 1
    # Сохраняем начальное состояние эксперимента
    experiments[exp_id] = {
        "topology": topology,
        "task_topology": task_topology,
        "strategy": strategy,
        "status": "starting",
        "result": None,
    }
    # Отправляем начальный статус по WebSocket всем подключенным клиентам
    for ws in active_connections:
        await ws.send_text(
            f"Эксперимент {exp_id} запускается (кластер: {topology}, задача: {task_topology}, стратегия: {strategy})"
        )

    # 3. Уведомляем GNS3 Manager о выбранной топологии через REST
    requests.post("http://localhost:8001/select_topology", json={"name": topology})

    # 4. Вызываем GNS3 VM Manager для создания виртуальной сети по выбранной топологии.
    # Передаём название топологии и токен авторизации для gns3server.
    resp = requests.post(
        "http://localhost:8002/start",
        json={"topology": topology, "token": GNS3_TOKEN},
    )
    vm_result = resp.json()
    # будем работать по IP, которые вернул VM-manager
    hosts = [n.get("ip_address") for n in vm_result.get("nodes", [])]
    hosts = [h for h in hosts if h]   # отфильтровали None
    # 5. Запрашиваем у Placement Engine mapping rank→host
    map_resp = requests.post(
        PLACEMENT_URL,
        json={
            "task_graph": {"processes": len(hosts)},
            "nodes": hosts,
            "strategy": strategy,
            "cluster_topology": topology,
            "task_topology": task_topology,
        },
    )
    mapping = map_resp.json()

    # 6-A. Отправляем rank/host-files на все VM
    master_vm = hosts[0]                 # упрощение: первый хост мастер
    rf_remote, hf_remote = push_openmpi_files_all(
        hosts,
        mapping["rankfile"],
        mapping["hostfile"]
    )

    # 6-B. Старт метрик
    token = requests.post(f"{METRICS_URL}/start",
                          json={"exp_id": exp_id}).json()["token"]

    # 6-C. Запускаем mpirun удалённо
    stdout, stderr = run_mpi(master_vm,
                             np=len(hosts),
                             rf=rf_remote)

    # 6-D. Финиш метрик
    exec_time = requests.post(f"{METRICS_URL}/finish",
                              json={"token": token}).json()["exec_time"]

    result = {"project": vm_result,
              "mapping": mapping,
              "exec_time": exec_time,
              "mpi_stdout": stdout,
              "mpi_stderr": stderr}


    # Обновляем статус и результат эксперимента в памяти
    experiments[exp_id]["status"] = "completed"
    experiments[exp_id]["result"] = result

    # 5. Отправляем финальное уведомление о завершении эксперимента через WebSocket
    for ws in active_connections:
        await ws.send_text(f"Эксперимент {exp_id} завершён. Результат: успех")

    # Возвращаем клиенту ID запущенного эксперимента (может использоваться для запроса результата)
    return {"experiment_id": exp_id}

@app.get("/experiments/{exp_id}/result")
def get_experiment_result(exp_id: int):
    """
    REST-метод для получения результата эксперимента по его ID.
    GUI может вызывать этот метод, чтобы получить итоговые данные после завершения.
    """
    exp = experiments.get(exp_id)
    if exp is None:
        return {"error": "Experiment not found"}
    return {
        "topology": exp["topology"],
        "task_topology": exp.get("task_topology"),
        "strategy": exp.get("strategy"),
        "status": exp["status"],
        "result": exp["result"],
    }

@app.websocket("/ws")
async def websocket_status(websocket: WebSocket):
    """
    WebSocket-эндпоинт для отправки статусов эксперимента в режиме реального времени на GUI.
    """
    # Принимаем новое WebSocket-соединение от клиента
    await websocket.accept()
    active_connections.append(websocket)
    try:
        # Удерживаем соединение открытым, слушая входящие (при необходимости)
        while True:
            _ = await websocket.receive_text()  # (Можно обрабатывать входящие сообщения от GUI, если нужно)
    except WebSocketDisconnect:
        # Удаляем соединение из списка при отключении
        active_connections.remove(websocket)


@app.on_event("shutdown")
def shutdown_event():
    """Terminate the gns3server process on shutdown."""
    global gns3_proc
    if gns3_proc and gns3_proc.poll() is None:
        gns3_proc.terminate()
        try:
            gns3_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            gns3_proc.kill()
