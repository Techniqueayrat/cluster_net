"""
placement_engine.main
Простейшая реализация «движка размещения».

– random  : случайное соответствие rank → host
– ordered : 0-й rank на 1-й host, 1-й rank на 2-й host …
"""

import random, json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict

app = FastAPI(title="Placement Engine")


class TaskGraph(BaseModel):
    processes: int                # N процессов
    # edges не используются в простых стратегиях, но поле оставим
    edges: List[List[int]] | None = None


class MapRequest(BaseModel):
    task_graph: TaskGraph
    nodes: List[str]              # hostnames / IP
    strategy: str = "random"      # random|ordered


@app.post("/map")
def make_mapping(data: MapRequest):
    n_proc = data.task_graph.processes
    hosts  = data.nodes

    if n_proc > len(hosts):
        raise HTTPException(400, f"need ≥ {n_proc} hosts, given {len(hosts)}")

    if data.strategy == "random":
        random.shuffle(hosts)
    elif data.strategy != "ordered":
        raise HTTPException(400, "unknown strategy")

    mapping = {rank: hosts[rank] for rank in range(n_proc)}

    # генерируем rankfile (OpenMPI) в виде текста
    rankfile_lines = [f"rank {r}={h} slot=0" for r, h in mapping.items()]
    rankfile_txt   = "\n".join(rankfile_lines)

    return {
        "mapping": mapping,        # rank -> host
        "rankfile": rankfile_txt,  # для записи на диск
        "hostfile": "\n".join(hosts[:n_proc])
    }
