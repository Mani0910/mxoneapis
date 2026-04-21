from fastapi import FastAPI
from dotenv import load_dotenv
from app.routes.builds import router as builds_router
from app.routes.status import router as status_router
from app.routes.transfer import router as transfer_router
from app.routes.ssh_execute import router as ssh_execute_router
from app.routes.upgrade import router as upgrade_router
from app.routes.download import router as download_router

load_dotenv()

app = FastAPI(
    title="MXOne Upgrade API",
    description=(
        "APIs for managing MX-ONE upgrades via S3 builds.\n\n"
        "**Typical flow:**\n"
        "1. `POST /ssh/installed` — check installed version on a VM\n"
        "2. `GET /builds/list?installed_version=7.2.0.0.0` — list builds available for upgrade\n"
        "3. `POST /builds/download` — download selected build from S3 onto the VM\n"
        "4. `GET /status` — poll until download completes\n"
        "5. `POST /mxone/upgrade/all` — run the full upgrade sequence\n"
        "6. `GET /status` — poll upgrade progress\n"
    ),
    version="2.0.0",
)

app.include_router(builds_router)
app.include_router(download_router)
app.include_router(transfer_router)
app.include_router(ssh_execute_router)
app.include_router(status_router)
app.include_router(upgrade_router)
