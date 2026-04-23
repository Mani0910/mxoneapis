import re
import threading
import logging

from fastapi import APIRouter

from app.models.request_models import DownloadRequest
from app.services.ssh_service import create_ssh_client
from app.services.build_service import get_build_bin_url
from app.services.progress_store import begin_operation, update_progress
from app.config import MXONE_REMOTE_DIR

router = APIRouter()
logger = logging.getLogger(__name__)


def _run_download(data: DownloadRequest):
    target = data.ip
    ssh = None
    try:
        update_progress(target, {
            "task": "download",
            "current_step": "resolve",
            "state": "connecting",
            "progress": 0,
            "message": f"Resolving build URL for '{data.build_name}'",
            "in_progress": 1,
        })

        bin_url, bin_file = get_build_bin_url(data.build_name)
        if not bin_url:
            update_progress(target, {
                "task": "download",
                "current_step": "error",
                "state": "error",
                "progress": 0,
                "message": f"No .bin file found for build: {data.build_name}",
                "in_progress": 0,
            })
            return

        update_progress(target, {
            "task": "download",
            "current_step": "connect",
            "state": "connecting",
            "progress": 2,
            "message": f"Connecting to {data.ip}",
            "in_progress": 1,
        })

        ssh = create_ssh_client(data.ip, data.username, data.password)
        dest = f"{MXONE_REMOTE_DIR}/{bin_file}"

        update_progress(target, {
            "task": "download",
            "current_step": "downloading",
            "state": "in_progress",
            "progress": 5,
            "message": f"Starting wget download of {bin_file} on {data.ip}",
            "destination": dest,
            "in_progress": 1,
        })

        command = (
            f"mkdir -p {MXONE_REMOTE_DIR} && "
            f"wget --progress=bar:force:noscroll -O {dest} {bin_url} 2>&1"
        )

        channel = ssh.get_transport().open_session()
        channel.set_combine_stderr(True)
        channel.exec_command(command)

        while not channel.exit_status_ready():
            if channel.recv_ready():
                chunk = channel.recv(4096).decode("utf-8", errors="ignore")
                matches = re.findall(r"(\d+)%", chunk)
                if matches:
                    pct = int(matches[-1])
                    update_progress(target, {
                        "task": "download",
                        "current_step": "downloading",
                        "state": "in_progress",
                        "progress": pct,
                        "message": f"Downloading {bin_file}: {pct}%",
                        "destination": dest,
                        "in_progress": 1,
                    })

        # Drain any remaining output
        while channel.recv_ready():
            chunk = channel.recv(4096).decode("utf-8", errors="ignore")
            matches = re.findall(r"(\d+)%", chunk)
            if matches:
                pct = int(matches[-1])
                update_progress(target, {
                    "task": "download",
                    "current_step": "downloading",
                    "state": "in_progress",
                    "progress": pct,
                    "message": f"Downloading {bin_file}: {pct}%",
                    "destination": dest,
                    "in_progress": 1,
                })

        exit_code = channel.recv_exit_status()

        if exit_code == 0:
            update_progress(target, {
                "task": "download",
                "current_step": "done",
                "state": "completed",
                "progress": 100,
                "message": f"Download complete: {bin_file} is ready at {dest}",
                "destination": dest,
                "in_progress": 0,
            })
        else:
            update_progress(target, {
                "task": "download",
                "current_step": "error",
                "state": "error",
                "progress": 0,
                "message": "wget exited with a non-zero status code",
                "in_progress": 0,
            })

    except Exception as e:
        logger.error(f"[DOWNLOAD] Failed on {target}: {e}")
        update_progress(target, {
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
def download_build(data: DownloadRequest):
    """
    Download a MX-ONE build directly onto the target VM via SSH wget.

    Typical flow:
    1. GET /builds/list  — pick a build tag (e.g. mx7.6.sp1.hf0.rc19)
    2. POST /builds/download  — pass that tag as build_name
    3. GET /status/download?ip=<ip>  — poll until state == completed
    """
    started, current = begin_operation(
        data.ip,
        "download",
        f"Starting download on {data.ip}",
    )
    if not started:
        return {
            "status": "busy",
            "message": f"Another operation is already in progress on {data.ip}.",
            "current": current,
        }

    thread = threading.Thread(target=_run_download, args=(data,), daemon=True)
    thread.start()

    return {
        "status": "started",
        "message": f"Download started for '{data.build_name}' on {data.ip}",
        "poll": f"GET /status/download?ip={data.ip}",
    }
