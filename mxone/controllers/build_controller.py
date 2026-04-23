# controllers/build_controller.py

from services.build_service import get_builds_service

def get_builds_controller():
    return get_builds_service()


from services.build_service import start_download_service

def start_download_controller(request):
    data = request.json
    return start_download_service(data)


from utils.job_store import jobs

def get_status_controller(ip):
    job = jobs.get(ip)

    if not job:
        return {"error": f"No active job found for IP: {ip}"}

    return job