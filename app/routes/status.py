import re
import socket
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from paramiko.ssh_exception import AuthenticationException, NoValidConnectionsError, SSHException
from app.models.request_models import StatusRequest
from app.services.ssh_service import create_ssh_client, execute_command
from app.services.progress_store import get_all_progress_by_task, get_progress

router = APIRouter()


def _parse_version_from_ts_about(output: str):
    for line in output.splitlines():
        m = re.search(r'(\d+\.\d+\.\d+\.\d+\.\d+)', line)
        if m:
            return m.group(1)
        m = re.search(r'(\d+)\.(\d+)\.sp(\d+)\.hf(\d+)\.rc(\d+)', line)
        if m:
            major, minor, sp, hf, rc = m.groups()
            return f"{major}.{minor}.{sp}.{hf}.{rc}"
    return None


# ─── Download status ──────────────────────────────────────────────────────────

@router.get("/status/download")
def get_download_status(ip: Optional[str] = Query(None, description="Target VM IP address")):
    """
    GET /status/download?ip=10.1.1.1  → status for that specific VM's download
    GET /status/download              → status of ALL active/recent downloads
    """
    if ip:
        return get_progress(ip.strip(), "download")
    return {"downloads": get_all_progress_by_task("download")}


# ─── Upgrade status ───────────────────────────────────────────────────────────

@router.get("/status/upgrade")
def get_upgrade_status(ip: Optional[str] = Query(None, description="Target VM IP address")):
    """
    GET /status/upgrade?ip=10.1.1.1  → status for that specific VM's upgrade
    GET /status/upgrade              → status of ALL active/recent upgrades
    """
    if ip:
        return get_progress(ip.strip(), "upgrade")
    return {"upgrades": get_all_progress_by_task("upgrade")}


# ─── VM health check (SSH + installed version) ───────────────────────────────

@router.post("/status")
def get_vm_status(data: StatusRequest):
    """
    Connect to a VM over SSH and return:
    - installed MX-ONE version (from ts_about)
    - current download status for that IP
    - current upgrade status for that IP
    """
    download_status = get_progress(data.ip, "download")
    upgrade_status = get_progress(data.ip, "upgrade")
    ssh = None

    try:
        ssh = create_ssh_client(data.ip, data.username, data.password)
        attempts = ["ts_about", "bash -lc 'ts_about'", "sh -lc 'ts_about'"]
        result = {"output": "", "error": "", "exit_status": None}
        for command in attempts:
            candidate = execute_command(ssh, command)
            result = candidate
            if candidate.get("output", "").strip() or candidate.get("exit_status") == 0:
                break

        installed_version = _parse_version_from_ts_about(result.get("output", ""))

        return {
            "status": "success",
            "target": data.ip,
            "installed_version": installed_version,
            "download": download_status,
            "upgrade": upgrade_status,
            "exit_status": result.get("exit_status"),
            "error": result.get("error", "").splitlines(),
        }

    except AuthenticationException:
        raise HTTPException(status_code=401, detail="SSH authentication failed.")
    except (NoValidConnectionsError, socket.timeout, TimeoutError):
        raise HTTPException(status_code=504, detail="Unable to reach target VM via SSH.")
    except SSHException as e:
        raise HTTPException(status_code=500, detail=f"SSH error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if ssh:
            try:
                ssh.close()
            except Exception:
                pass
