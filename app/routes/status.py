import re
import socket
from fastapi import APIRouter, HTTPException
from paramiko.ssh_exception import AuthenticationException, NoValidConnectionsError, SSHException
from app.models.request_models import StatusRequest
from app.services.ssh_service import create_ssh_client, execute_command
from app.services.progress_store import get_all_progress, get_progress

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


def _idle_task_status(task: str, target: str = ""):
    payload = {
        "task": task,
        "current_step": "",
        "state": "idle",
        "progress": 0,
        "message": "",
        "in_progress": 0,
    }
    if target:
        payload["target"] = target
    return payload


def _task_status_for_target(task: str, target: str):
    current = get_progress(target)
    if current.get("task") == task:
        return current
    return _idle_task_status(task, target)


def _task_status_for_all(task: str):
    all_targets = get_all_progress()
    filtered = {
        target: status
        for target, status in all_targets.items()
        if status.get("task") == task
    }
    return {"targets": filtered}


@router.get("/status")
def get_status(ip: str = "", host: str = "", all_targets: bool = False):
    target = (ip or host or "").strip()
    if target:
        return get_progress(target)

    if all_targets:
        return {"targets": get_all_progress()}

    # Backward-compatible default: return only latest status object (single payload).
    return get_progress()


@router.get("/status/download")
def get_download_status(ip: str = "", host: str = "", all_targets: bool = False):
    target = (ip or host or "").strip()
    if target:
        return _task_status_for_target("download", target)

    if all_targets:
        return _task_status_for_all("download")

    latest = get_progress()
    if latest.get("task") == "download":
        return latest
    return _idle_task_status("download")


@router.get("/status/upgrade")
def get_upgrade_status(ip: str = "", host: str = "", all_targets: bool = False):
    target = (ip or host or "").strip()
    if target:
        return _task_status_for_target("upgrade", target)

    if all_targets:
        return _task_status_for_all("upgrade")

    latest = get_progress()
    if latest.get("task") == "upgrade":
        return latest
    return _idle_task_status("upgrade")


@router.post("/status")
def get_status_for_target(data: StatusRequest):
    """
    Return status only for the requested target IP.
    Also connects to the target over SSH and fetches installed version via ts_about.
    """
    operation_status = get_progress(data.ip)
    ssh = None

    try:
        ssh = create_ssh_client(data.ip, data.username, data.password)
        attempts = [
            "ts_about",
            "bash -lc 'ts_about'",
            "sh -lc 'ts_about'",
        ]
        result = {"output": "", "error": "", "exit_status": None}
        for command in attempts:
            candidate = execute_command(ssh, command)
            has_output = bool(candidate.get("output", "").strip())
            exit_ok = candidate.get("exit_status") == 0
            result = candidate
            if has_output or exit_ok:
                break

        output_text = result.get("output", "")
        error_text = result.get("error", "")
        installed_version = _parse_version_from_ts_about(output_text)

        return {
            "status": "success",
            "target": data.ip,
            "operation_status": operation_status,
            "installed_version": installed_version,
            "exit_status": result.get("exit_status"),
            "error": error_text.splitlines(),
        }

    except AuthenticationException:
        raise HTTPException(status_code=401, detail="SSH authentication failed.")
    except (NoValidConnectionsError, socket.timeout, TimeoutError):
        raise HTTPException(
            status_code=504,
            detail=(
                "Unable to reach target VM via SSH from this API server. "
                "Ensure network route/firewall allows SSH from API host to target IP."
            ),
        )
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