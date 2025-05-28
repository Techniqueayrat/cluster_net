"""
placement_engine.main
Расчёт размещения MPI-задачи по выбранной стратегии.

Поддерживаемые стратегии:
– simple   : выбор узлов по порядку
– random   : случайное соответствие rank → host
– optimal  : учитывает топологию кластера
– advanced : использует оптимальное размещение и
              корректирует его под топологию задачи
"""

import random, json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List

app = FastAPI(title="Placement Engine")


class TaskGraph(BaseModel):
    processes: int                # N процессов
    # edges не используются в простых стратегиях, но поле оставим
    edges: List[List[int]] | None = None


class MapRequest(BaseModel):
    task_graph: TaskGraph
    nodes: List[str]              # hostnames / IP
    strategy: str = "simple"      # simple|random|optimal|advanced
    cluster_topology: str | None = None
    task_topology: str | None = None


@app.post("/map")
def _optimal_order(hosts: List[str], topology: str | None) -> List[str]:
    """Return hosts ordered with basic cluster topology awareness."""
    if topology in {"fat-tree", "thin-tree"}:
        return sorted(hosts)
    if topology == "torus":
        return hosts  # already near-optimal for toy example
    return hosts


def _advanced_order(
    hosts: List[str], cluster_topology: str | None, task_topology: str | None
) -> List[str]:
    hosts = list(_optimal_order(hosts, cluster_topology))
    if task_topology == "GRID":
        return hosts[::-1]
    if task_topology == "CUBE":
        mid = len(hosts) // 2
        return hosts[mid:] + hosts[:mid]
    return hosts


def make_mapping(data: MapRequest):
    n_proc = data.task_graph.processes
    hosts = list(data.nodes)

    if n_proc > len(hosts):
        raise HTTPException(400, f"need ≥ {n_proc} hosts, given {len(hosts)}")

    strat = data.strategy.lower()

    if strat == "simple":
        pass
    elif strat == "random":
        random.shuffle(hosts)
    elif strat == "optimal":
        hosts = _optimal_order(hosts, data.cluster_topology)
    elif strat == "advanced":
        hosts = _advanced_order(hosts, data.cluster_topology, data.task_topology)
    else:
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

