"""
metrics_collector.main
Мини-сервис: фиксирует t_start / t_end и отдаёт exec_time.
Можно дополнять CPU/Net-метриками позже.
"""

import time, uuid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Metrics Collector")
active: dict[str, float] = {}   # id -> t_start
done:   dict[str, float] = {}   # id -> exec_time


class StartReq(BaseModel):
    exp_id: int


class EndReq(BaseModel):
    token: str


@app.post("/start")
def start(req: StartReq):
    token = str(uuid.uuid4())
    active[token] = time.time()
    return {"token": token}


@app.post("/finish")
def finish(req: EndReq):
    t0 = active.pop(req.token, None)
    if t0 is None:
        raise HTTPException(404, "unknown token")
    exec_time = time.time() - t0
    done[req.token] = exec_time
    return {"exec_time": exec_time}


@app.get("/metrics/{token}")
def get_metrics(token: str):
    if token not in done:
        raise HTTPException(404, "metrics not found")
    return {"exec_time": done[token]}
