from fastapi import APIRouter, HTTPException
from app.models.request_models import TransferRequest
from app.services.ssh_service import create_ssh_client
from app.services.progress_store import progress_data
from app.config import BUILD_PATH, MXONE_REMOTE_DIR
from scp import SCPClient
import os
import threading

router = APIRouter()


@router.post("/transfer")
def transfer_build(data: TransferRequest):

    local_path = os.path.join(BUILD_PATH, data.build_name)

    if not os.path.isfile(local_path):
        raise HTTPException(404, "Build not found")

    progress_data.update({
        "task": "transfer",
        "current_step": "connect",
        "state": "connecting",
        "progress": 0,
        "message": f"Connecting to {data.ip}",
        "in_progress": 1
    })

    def run_transfer():
        ssh = None
        scp = None
        last_pct = -1

        try:
            print(f"[TRANSFER] Connecting to {data.ip}", flush=True)
            ssh = create_ssh_client(data.ip, data.username, data.password)
            ssh.exec_command(f"mkdir -p {MXONE_REMOTE_DIR}")
            print("[TRANSFER] Upload started", flush=True)

            progress_data.update({
                "task": "transfer",
                "current_step": "upload",
                "state": "uploading",
                "progress": 0,
                "message": f"Uploading {data.build_name}",
                "in_progress": 1
            })

            def progress(filename, size, sent):
                nonlocal last_pct
                pct = int((sent / size) * 100) if size else 0
                progress_data["progress"] = pct
                progress_data["message"] = f"Uploading {data.build_name}"
                if pct % 10 == 0 and pct != last_pct:
                    last_pct = pct
                    print(f"[TRANSFER] {data.build_name}: {pct}%", flush=True)

            scp = SCPClient(ssh.get_transport(), progress=progress)
            scp.put(local_path, f"{MXONE_REMOTE_DIR}/{data.build_name}")

            progress_data.update({
                "task": "transfer",
                "current_step": "done",
                "state": "completed",
                "progress": 100,
                "message": "Transfer completed",
                "in_progress": 0
            })
            print("[TRANSFER] Completed", flush=True)

        except Exception as e:
            progress_data.update({
                "task": "transfer",
                "current_step": "error",
                "state": "error",
                "progress": 0,
                "message": str(e),
                "in_progress": 0
            })
            print(f"[TRANSFER] Error: {e}", flush=True)

        finally:
            try:
                if scp:
                    scp.close()
            except Exception:
                pass
            try:
                if ssh:
                    ssh.close()
            except Exception:
                pass

    threading.Thread(target=run_transfer, daemon=True).start()

    return {
        "status": "started",
        "message": f"Transfer of {data.build_name} to {data.ip} has started"
        
    }