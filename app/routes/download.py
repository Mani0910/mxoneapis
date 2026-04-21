import threading
import logging

from fastapi import APIRouter, HTTPException

from app.models.request_models import DownloadRequest
from app.services.ssh_service import create_ssh_client
from app.services.s3_service import generate_presigned_url
from app.services.progress_store import progress_data
from app.config import MXONE_REMOTE_DIR

router = APIRouter()
logger = logging.getLogger(__name__)


def _run_download(data: DownloadRequest):
    ssh = None
    try:
        progress_data.update({
            "task": "download",
            "current_step": "connect",
            "state": "connecting",
            "progress": 0,
            "message": f"Connecting to {data.ip}",
            "in_progress": 1,
        })

        ssh = create_ssh_client(data.ip, data.username, data.password)
        ssh.exec_command(f"mkdir -p {MXONE_REMOTE_DIR}")

        progress_data.update({
            "task": "download",
            "current_step": "generate_url",
            "state": "in_progress",
            "progress": 5,
            "message": "Generating secure download URL from S3",
            "in_progress": 1,
        })

        # Presigned URL valid for 2 hours — plenty of time for large .bin files
        url = generate_presigned_url(data.build_name, expiry_seconds=7200)
        dest = f"{MXONE_REMOTE_DIR}/{data.build_name}"

        progress_data.update({
            "task": "download",
            "current_step": "downloading",
            "state": "in_progress",
            "progress": 10,
            "message": f"Downloading {data.build_name} on {data.ip} (this may take several minutes)",
            "in_progress": 1,
        })

        logger.info(f"[DOWNLOAD] Starting wget on {data.ip} → {dest}")

        # Run wget on the remote VM; -q silences progress bar noise in logs
        # timeout=7200 (2h) matches the presigned URL expiry
        wget_cmd = f'wget -q -O "{dest}" "{url}"'
        _, stdout, stderr = ssh.exec_command(wget_cmd, timeout=7200)
        exit_code = stdout.channel.recv_exit_status()

        if exit_code != 0:
            err_output = stderr.read().decode(errors="ignore").strip()
            raise Exception(f"wget exited with code {exit_code}: {err_output}")

        logger.info(f"[DOWNLOAD] Completed: {data.build_name} on {data.ip}")

        progress_data.update({
            "task": "download",
            "current_step": "done",
            "state": "completed",
            "progress": 100,
            "message": f"Download complete: {data.build_name} is ready at {dest}",
            "in_progress": 0,
        })

    except Exception as e:
        logger.error(f"[DOWNLOAD] Failed: {e}")
        progress_data.update({
            "task": "download",
            "current_step": "error",
            "state": "error",
            "progress": 0,
            "message": str(e),
            "in_progress": 0,
        })

    finally:
        if ssh:
            try:
                ssh.close()
            except Exception:
                pass


@router.post("/builds/download")
def download_build_to_vm(data: DownloadRequest):
    """
    Download a build from S3 directly onto the target VM using wget over SSH.

    Steps:
      1. SSH into the VM
      2. Generate a short-lived presigned S3 URL
      3. Run wget on the VM to pull the file into /local/home/mxone_admin/ (default)

    Poll GET /status to track progress.
    Once state == 'completed', you can call POST /mxone/upgrade/all to start the upgrade.
    """
    if progress_data.get("in_progress") == 1:
        return {
            "status": "busy",
            "message": "Another operation is already in progress.",
            "current": progress_data.copy(),
        }

    threading.Thread(target=_run_download, args=(data,), daemon=True).start()

    return {
        "status": "started",
        "message": f"Download of {data.build_name} to {data.ip}:{MXONE_REMOTE_DIR} has started.",
        "poll": "GET /status",
    }
