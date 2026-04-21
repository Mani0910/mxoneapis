from fastapi import APIRouter, HTTPException
from app.models.request_models import UpgradeRequest
from app.services.upgrade_service import run_full_upgrade
from app.services.progress_store import progress_data
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/mxone/upgrade/all")
def upgrade_all(data: UpgradeRequest):
    """
    Start the full MX-ONE upgrade sequence on the target host:
      1. Distribute build package
      2. Prepare upgrade
      3. SN upgrade (may reboot)
      4. SNM upgrade
      5. PM upgrade
      6. Restart jboss

    Poll GET /status for live progress.

    Prerequisites:
      - The build file must already be present on the VM at /local/home/mxone_admin/.
        Use POST /builds/download first if it is not.
      - version format: "7.6.1.0.19"  (major.minor.sp.hf.rc)
    """
    if progress_data.get("in_progress") == 1:
        return {
            "status": "busy",
            "message": "Another operation is already in progress.",
            "current": progress_data.copy(),
        }

    try:
        logger.info(f"Received upgrade request for host: {data.host}, version: {data.version}")
        result = run_full_upgrade(data)
        return {"status": "success", "data": result}

    except Exception as e:
        logger.error(f"Upgrade failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upgrade failed: {str(e)}")
