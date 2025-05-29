from fastapi import FastAPI
import requests
import uuid
import re
import pathlib
import socket
import time
from typing import Optional, Dict, Any, List

app = FastAPI(title="GNS3 VM Manager (extended)")
GNS3_SERVER_URL = "http://localhost:3080"
IP_BASE = "10.0.0."  

# ------------------------------------------------------------------
# Telnet helpers
# ------------------------------------------------------------------

def _set_ip_via_telnet(console_host: str, console_port: int,
                       ip_cidr: str, iface: str = "ens3") -> None:
    """Подключается к консоли гостя и назначает IP интерфейсу."""
    with socket.create_connection((console_host, console_port), timeout=8) as s:
        def send(cmd: str) -> None:
            s.sendall(cmd.encode() + b"\n")
            time.sleep(0.2)

        # login: root / 0000
        send("")            # wake up console
        time.sleep(3)
        s.recv(1024)
        send("root")
        time.sleep(0.3)
        s.recv(1024)
        send("0000")
        time.sleep(0.3)
        s.recv(1024)
        send(f"ip link set {iface} up")
        send(f"ip addr add {ip_cidr} dev {iface}")
        # send("ssh-keygen -A")        # создаёт /etc/ssh/ssh_host_*,
        send("systemctl enable --now sshd")
        send("exit")



# --------------------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------------------

_name_safe_re = re.compile(r"[^A-Za-z0-9_-]+")


def _sanitize(name: str) -> str:
    """Return a GNS3‑safe node/template name (no dots, spaces, …)."""
    return _name_safe_re.sub("_", name)


_alnum_only = re.compile(r"[^A-Za-z0-9]+")

def _clean_alnum(s: str) -> str:
    return _alnum_only.sub("", s)


def _open_project(project_id: str, headers: Dict[str, str]) -> None:
    """Ensure the project is opened inside GNS3."""
    resp = requests.post(
        f"{GNS3_SERVER_URL}/v3/projects/{project_id}/open", headers=headers
    )
    if resp.status_code == 409:  # already open
        print(f"Project {project_id} already open")
        return
    resp.raise_for_status()
    print(f"Project {project_id} opened")


# --------------------------------------------------------------------------------------
# Internal helpers used by the API logic
# --------------------------------------------------------------------------------------

def _get_or_create_project(name: str, headers: Dict[str, str]) -> Dict[str, Any]:
    """Return project object; create if it does not exist."""
    projects = requests.get(f"{GNS3_SERVER_URL}/v3/projects", headers=headers).json()
    for p in projects:
        if p.get("name") == name:
            print(f"Found existing project '{name}' (id={p['project_id']})")
            _open_project(p["project_id"], headers)
            return p

    resp = requests.post(
        f"{GNS3_SERVER_URL}/v3/projects",
        headers=headers,
        json={"name": name},
    )
    resp.raise_for_status()
    project = resp.json()
    print(f"Created new project '{name}' (id={project['project_id']})")
    _open_project(project["project_id"], headers)
    return project


def _get_arch_image(headers: Dict[str, str]) -> Optional[str]:
    """Return the *first* QEMU image whose filename starts with 'arch'."""
    images_resp = requests.get(
        f"{GNS3_SERVER_URL}/v3/images", params={"image_type": "qemu"}, headers=headers
    )
    images_resp.raise_for_status()
    for img in images_resp.json():
        # The API returns the *basename* in `filename`, full path in `file_path`
        filename = img.get("filename") or ""
        if filename.startswith("arch"):
            return img.get("file_path") or filename
    return None


def _get_or_create_qemu_template(
    template_name: str,
    image: str,
    ram: int,
    platform: Optional[str],
    headers: Dict[str, str],
) -> str:
    """Return `template_id`; create QEMU template when missing.

    The creation flow was updated to:
      • *Always* fetch the image list (`GET /v3/images?image_type=qemu`) and pick
        the first object whose **filename** begins with ``arch``.  If none is
        found, we quietly fall back to the provided *image* argument.
      • Use the *flat* template JSON format expected by GNS3 3.x, closely
        matching the example you supplied.
    """

    clean_name = _clean_alnum(template_name)

    # 1. Search for an existing template with the same (cleaned) name ---------
    for t in requests.get(f"{GNS3_SERVER_URL}/v3/templates", headers=headers).json():
        if t.get("name") == clean_name:
            print(f"Found QEMU template '{clean_name}' (id={t['template_id']})")
            return t["template_id"]

    # 2. Select the disk image ------------------------------------------------
    image_path = _get_arch_image(headers) or image

    # 3. Prepare creation payload (flat, GNS3 3.x style) ----------------------
    payload: Dict[str, Any] = {
        "name": clean_name,
        "default_name_format": "{name}-{0}",
        "usage": "",
        "symbol": "qemu_guest",
        "category": "guest",
        "port_name_format": "Ethernet{0}",
        "port_segment_size": 0,
        "first_port_name": "",
        "custom_adapters": [],
        "hda_disk_image": image_path,
        "hdb_disk_image": "",
        "hdc_disk_image": "",
        "hdd_disk_image": "",
        "hda_disk_interface": "ide",
        "hdb_disk_interface": "none",
        "hdc_disk_interface": "none",
        "hdd_disk_interface": "none",
        "cdrom_image": "",
        "bios_image": "",
        "boot_priority": "c",
        "console_type": "telnet",
        "console_auto_start": False,
        "aux_type": "none",
        "ram": ram,
        "cpus": 1,
        "adapters": 1,
        "adapter_type": "e1000",
        "mac_address": "",
        "replicate_network_connection_state": True,
        "tpm": False,
        "uefi": False,
        "create_config_disk": False,
        "on_close": "power_off",
        "platform": platform or "x86_64",
        "qemu_path": "",
        "cpu_throttling": 0,
        "process_priority": "normal",
        "options": "",
        "kernel_image": "",
        "initrd": "",
        "kernel_command_line": "",
        "linked_clone": True,
        "compute_id": "local",
        "template_type": "qemu",
    }

    resp = requests.post(f"{GNS3_SERVER_URL}/v3/templates", headers=headers, json=payload)
    resp.raise_for_status()
    tid = resp.json()["template_id"]
    print(f"Created QEMU template '{clean_name}' (id={tid})")
    return tid


def _create_node_from_template(
    project_id: str,
    template_id: str,
    x: int,
    y: int,
    name: Optional[str],
    headers: Dict[str, str],
) -> Dict[str, Any]:
    """Instantiate a node from an existing template, positioned at (x, y)."""
    payload: Dict[str, Any] = {"x": x, "y": y}
    if name:
        payload["name"] = _sanitize(name)

    resp = requests.post(
        f"{GNS3_SERVER_URL}/v3/projects/{project_id}/templates/{template_id}",
        headers=headers,
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()


def _create_links(
    project_id: str,
    link_defs: List[Dict[str, Any]],
    node_ids: Dict[str, str],
    headers: Dict[str, str],
):
    """
    Создаёт связи так, как того требует GNS3 3.x:
      • каждая связь содержит список «nodes» c node_id/adapter_number/port_number
      • можно заранее указать adapter/port в JSON-топологии; иначе берём 0:0
      • добавляем обязательные поля link_type и suspend
    Пример POST /v3/projects/<pid>/links
    {
        "link_type": "ethernet",
        "suspend": false,
        "nodes": [
            {"node_id": "...", "adapter_number": 0, "port_number": 0},
            {"node_id": "...", "adapter_number": 0, "port_number": 0}
        ]
    }
    """
    for link in link_defs:
        endpoints = link.get("endpoints", [])
        if len(endpoints) < 2:
            continue

        nodes_payload = []
        for ep in endpoints:
            # a) упрощённый формат: "N1"
            if isinstance(ep, str):
                ep_name, adapter, port = ep, 0, 0
            # b) расширенный: {"node": "N1", "adapter": 1, "port": 0}
            else:
                ep_name = ep.get("node") or ep.get("name") or ep.get("id")
                adapter = ep.get("adapter", ep.get("adapter_number", 0))
                port = ep.get("port", ep.get("port_number", 0))

            nodes_payload.append(
                {
                    "node_id": node_ids[ep_name],
                    "adapter_number": adapter,
                    "port_number": port,
                }
            )

        link_data = {
            "link_type": link.get("link_type", "ethernet"),
            "suspend": False,
            "nodes": nodes_payload,
        }

        requests.post(
            f"{GNS3_SERVER_URL}/v3/projects/{project_id}/links",
            headers=headers,
            json=link_data,
        )
        print(f"Created link {endpoints[0]} <-> {endpoints[1]}")


def _normalize_topology(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return topology description in the simplified internal format."""
    if "topology" not in config:
        return config

    topo = config.get("topology", {})

    nodes: List[Dict[str, Any]] = []
    for n in topo.get("nodes", []):
        n_type = n.get("node_type") or n.get("type")
        entry = {
            "id": n.get("node_id") or n.get("name"),
            "name": n.get("name"),
            "type": n_type,
            "x": n.get("x", 0),
            "y": n.get("y", 0),
        }
        if n_type == "qemu":
            props = n.get("properties", {})
            entry["image"] = props.get("hda_disk_image") or n.get("image", "")
            entry["ram"] = props.get("ram", n.get("ram", 512))
            if props.get("platform"):
                entry["platform"] = props.get("platform")

        nodes.append(entry)

    links: List[Dict[str, Any]] = []
    for link in topo.get("links", []):
        eps = []
        for ep in link.get("nodes", []):
            eps.append(
                {
                    "node": ep.get("node_id"),
                    "adapter": ep.get("adapter_number", 0),
                    "port": ep.get("port_number", 0),
                }
            )
        if eps:
            links.append({"endpoints": eps})

    return {"nodes": nodes, "links": links}


# --------------------------------------------------------------------------------------
# API endpoint
# --------------------------------------------------------------------------------------

@app.post("/start")
def start_topology(payload: dict):
    """Launch (or reuse) a virtual topology inside GNS3 server.

    The function strictly follows these steps, mirroring the captured HTTP flow:
       1) Ensure the project exists (create when absent)
       2) Ensure the required QEMU template exists for every unique QCOW2 image
       3) Instantiate nodes from templates
       4) Create links
       5) Start all nodes
    """

    topology_name = payload.get("topology")
    if not topology_name:
        return {"error": "topology not provided"}

    token = payload.get("token")
    if not token:
        return {"error": "token missing"}

    headers = {"Authorization": f"Bearer {token}"}

    # ------------------------------------------------------------------
    # Step 0. Fetch JSON definition from the (external) Topology Manager
    # ------------------------------------------------------------------
    cfg_resp = requests.get(f"http://localhost:8001/topologies/{topology_name}")
    if cfg_resp.status_code != 200:
        return {"error": "Topology configuration not found", "topology": topology_name}

    config = _normalize_topology(cfg_resp.json())

    project_name = f"project_{topology_name}"

    # ------------------------------------------------------------------
    # Step 1. Ensure project exists
    # ------------------------------------------------------------------
    project = _get_or_create_project(project_name, headers)
    project_id = project["project_id"]

    # ------------------------------------------------------------------
    # Step 2. Ensure templates exist and build image→template map
    # ------------------------------------------------------------------
    template_for_image: Dict[str, str] = {}
    for node in config.get("nodes", []):
        if node.get("type", "qemu") != "qemu":
            continue  # Non‑QEMU nodes are handled later
        image_path = node.get("image")
        if image_path in template_for_image:
            continue  # already done
        template_name = f"tpl_{pathlib.Path(image_path).name}"  # e.g. tpl_arch3.qcow
        template_id = _get_or_create_qemu_template(
            template_name=template_name,
            image=image_path,
            ram=node.get("ram", 512),
            platform=node.get("platform"),
            headers=headers,
        )
        template_for_image[image_path] = template_id

    # ------------------------------------------------------------------
    # Step 3. Create nodes (from templates or directly)
    # ------------------------------------------------------------------
    node_ids: Dict[str, str] = {}

    for node in config.get("nodes", []):
        if node.get("type", "qemu") == "qemu":
            base = pathlib.Path(node["image"]).stem  # arch3 → "arch3"
            template_basename = base  # <- used for autogenerated node name
            template_id = template_for_image[node["image"]]

            node_name = node.get("name") or f"{template_basename}-{uuid.uuid4().hex[:4]}"
            created = _create_node_from_template(
                project_id,
                template_id,
                x=node.get("x", 0),
                y=node.get("y", 0),
                name=node_name,
                headers=headers,
            )
        else:
            # Other node types (e.g. Ethernet switch, Docker) – create directly
            node_data = {
                "name": node["name"],
                "node_type": node.get("node_type", node.get("type")),
                "compute_id": "local",
                "x": node.get("x", 0),
                "y": node.get("y", 0),
            }
            res = requests.post(
                f"{GNS3_SERVER_URL}/v3/projects/{project_id}/nodes", headers=headers, json=node_data
            )
            res.raise_for_status()
            created = res.json()

        # Use the node's *configured* name as the key inside `node_ids`
        node_key = node.get("name") or template_basename  # fall back to template base
        node_ids[node_key] = created["node_id"]
        node_key_id = node.get("id")                                  # N1
        if node_key_id:
            node_ids[node_key_id] = created["node_id"]   
        print(f"Node '{node_key}' ready (id={node_ids[node_key]})")

    # ------------------------------------------------------------------
    # Step 4. Create links
    # ------------------------------------------------------------------
    _create_links(project_id, config.get("links", []), node_ids, headers)

    # ------------------------------------------------------------------
    # Step 5. Start all nodes
    # ------------------------------------------------------------------
    start_resp = requests.post(
        f"{GNS3_SERVER_URL}/v3/projects/{project_id}/nodes/start", headers=headers
    )
    start_resp.raise_for_status()
    print("All nodes started for project", project_id)

    # ------------------------------------------------------------------
    # Gather final node information (statuses, hosts, …)
    # ------------------------------------------------------------------
    nodes_status = requests.get(
        f"{GNS3_SERVER_URL}/v3/projects/{project_id}/nodes", headers=headers
    ).json()

    # sequential IP assignment only for QEMU nodes --------------------
    qemu_nodes = [n for n in nodes_status if n.get("node_type") == "qemu"]
    time.sleep(30)
    for idx, node in enumerate(qemu_nodes, start=1):
        ip = f"{IP_BASE}{idx}"
        cidr = f"{ip}/24"
        try:
            _set_ip_via_telnet("127.0.0.1", node["console"], cidr)
            node["ip_address"] = ip
            print(f"Configured {node['name']} → {ip}")
        except Exception as e:
            print(f"[WARN] could not configure IP on {node['name']}: {e}")
    return {"project_id": project_id, "nodes": nodes_status}