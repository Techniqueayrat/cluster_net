import paramiko
import io
import time
from typing import Sequence

SSH_USER = "root"
SSH_PASS = "0000"
REMOTE_TMP = "/tmp/mpi_experiment"  # куда копировать hostfile/rankfile
def _client(host: str, timeout=8) -> paramiko.SSHClient:
    cl = paramiko.SSHClient()
    cl.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cl.connect(
        hostname=host,
        username=SSH_USER,
        password=SSH_PASS,
        look_for_keys=False,
        allow_agent=False,
        timeout=timeout,
    )
    return cl

def scp_text(host: str, text: str, remote_path: str):
    cl = _client(host)
    sftp = cl.open_sftp()
    try:
        # убеждаемся, что /tmp/mpi_experiment существует
        try:
            sftp.stat(REMOTE_TMP)
        except FileNotFoundError:
            sftp.mkdir(REMOTE_TMP)
        with sftp.file(remote_path, "w") as f:
            f.write(text)
    finally:
        sftp.close(); cl.close()

def exec_ssh(host: str, cmd: str, timeout=0):
    cl = _client(host)
    try:
        stdin, stdout, stderr = cl.exec_command(cmd, timeout=timeout)
        return stdout.read().decode(), stderr.read().decode()
    finally:
        cl.close()

def push_openmpi_files(master_ip: str, rankfile: str, hostfile: str):
    """Копирует rankfile и hostfile на master-VM."""
    rf_remote = f"{REMOTE_TMP}/rankfile"
    hf_remote = f"{REMOTE_TMP}/hostfile"
    scp_text(master_ip, rankfile, rf_remote)
    scp_text(master_ip, hostfile, hf_remote)
    return rf_remote, hf_remote

def push_openmpi_files_all(hosts: Sequence[str], rankfile: str, hostfile: str):
    """Копирует rankfile и hostfile на каждую VM."""
    rf_remote = f"{REMOTE_TMP}/rankfile"
    hf_remote = f"{REMOTE_TMP}/hostfile"
    for host in hosts:
        scp_text(host, rankfile, rf_remote)
        scp_text(host, hostfile, hf_remote)
    return rf_remote, hf_remote

def run_mpi(master_ip: str, np: int, rf: str):
    """Запускает mpirun на master‑хосте, отключая проверку SSH‑ключей."""
    ssh_opts = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
    mca = f"OMPI_MCA_plm_rsh_agent='ssh {ssh_opts}'"
    cmd = f"{mca} mpirun -np {np} --rankfile {rf} /usr/bin/mpi_hello"
    out, err = exec_ssh(master_ip, cmd)
    return out, err
