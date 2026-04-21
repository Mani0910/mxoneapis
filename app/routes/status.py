from fastapi import APIRouter
from app.services.progress_store import progress_data

router = APIRouter()


@router.get("/status")
def get_status():
    return progress_data