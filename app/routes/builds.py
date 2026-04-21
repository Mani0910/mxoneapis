from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.services.s3_service import list_s3_builds

router = APIRouter()


@router.get("/builds/list")
def list_builds(installed_version: Optional[str] = Query(
    None,
    description="If provided, only return builds with a version higher than this. "
                "Accepts formats: '7.2', '7.6.1.0.19', or '7.6.sp1.hf0.rc19'."
)):
    """
    List MX-ONE builds available in S3.
    Pass ?installed_version=7.2 to filter builds that are upgrades above the installed version.
    """
    try:
        builds = list_s3_builds(installed_version)
        return {
            "builds": builds,
            "count": len(builds),
            "filter_above": installed_version or "none",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
