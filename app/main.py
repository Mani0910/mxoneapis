from fastapi import FastAPI
import re
from dotenv import load_dotenv
from app.routes.builds import router as builds_router
from app.routes.status import router as status_router
from app.routes.ssh_execute import router as ssh_execute_router
from app.routes.upgrade import router as upgrade_router
from app.routes.download import router as download_router

load_dotenv()

app = FastAPI(
    title="MXOne Upgrade API",
    description=(
        "APIs for managing MX-ONE upgrades.\n\n"
        "**Typical flow:**\n"
        "1. `POST /mxone/installed` — check installed version on a VM\n"
        "2. `GET /builds/list?installed_version=7.6.1.0.19` — list available builds (upgrades only)\n"
        "3. `POST /builds/download` — download selected build onto the VM via SSH wget\n"
        "4. `GET /status/download?ip=<ip>` — poll until download state == completed\n"
        "5. `POST /mxone/upgrade/all` — run the full upgrade sequence\n"
        "6. `GET /status/upgrade?ip=<ip>` — poll upgrade progress\n"
    ),
    version="3.0.0",
)


@app.middleware("http")
async def normalize_duplicate_slashes(request, call_next):
    # Some clients send paths like //builds/list; normalize to avoid 404.
    path = request.scope.get("path", "")
    if "//" in path:
        request.scope["path"] = re.sub(r"/{2,}", "/", path)
    return await call_next(request)

app.include_router(builds_router)
app.include_router(download_router)
app.include_router(ssh_execute_router)
app.include_router(status_router)
app.include_router(upgrade_router)
