from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.services.build_service import list_builds as _list_builds

router = APIRouter()


@router.get("/builds/list")
def list_builds(installed_version: Optional[str] = Query(
    None,
    description="If provided, only return builds with a version higher than this. "
                "Accepts format: '7.2', '7.6.1.0.19'."
)):
    """
    List MX-ONE builds available on the release server.
    Pass ?installed_version=7.6.1.0.19 to filter to upgrades only.
    """
    try:
        builds = _list_builds(installed_version)
        return {
            "builds": builds,
            "count": len(builds),
            "filter_above": installed_version or "none",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
