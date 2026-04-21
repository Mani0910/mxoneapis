import re
from fastapi import APIRouter, HTTPException
from app.models.request_models import SSHCommandRequest
from app.services.ssh_service import create_ssh_client, execute_command

router = APIRouter()


def _parse_version_from_ts_about(output: str) -> str | None:
    """
    Extract the MX-ONE version from ts_about output.
    Tries 5-part dotted (7.6.1.0.19) first, then sp/hf/rc style.
    Returns a normalised 5-part version string or None.
    """
    for line in output.splitlines():
        # 5-part dotted version: 7.6.1.0.19
        m = re.search(r'(\d+\.\d+\.\d+\.\d+\.\d+)', line)
        if m:
            return m.group(1)
        # build-file style in a line: 7.6.sp1.hf0.rc19
        m = re.search(r'(\d+)\.(\d+)\.sp(\d+)\.hf(\d+)\.rc(\d+)', line)
        if m:
            major, minor, sp, hf, rc = m.groups()
            return f"{major}.{minor}.{sp}.{hf}.{rc}"
    return None


@router.post("/ssh/installed")
def get_installed_version(data: SSHCommandRequest):
    """
    Connect to a VM via SSH, run ts_about, and return the installed MX-ONE version.
    Use the returned installed_version as the ?installed_version= param on GET /builds/list
    to see only builds that are upgrades.
    """
    try:
        ssh = create_ssh_client(data.ip, data.username, data.password)
        try:
            # First try plain command; if PATH is missing in non-interactive shell,
            # retry through a login shell.
            result = execute_command(ssh, "ts_about")
            if not result.get("output", "").strip():
                result = execute_command(ssh, "bash -lc 'ts_about'")
        finally:
            ssh.close()

        output_text = result.get("output", "")
        error_text = result.get("error", "")
        output_lines = output_text.splitlines()
        version = _parse_version_from_ts_about(output_text)

        if not output_text.strip() and error_text.strip():
            raise HTTPException(
                status_code=500,
                detail=f"ts_about failed: {error_text.strip()}",
            )

        return {
            "status": "success",
            "MX-One Server": data.ip,
            "installed_version": version,
            "output": output_lines,
            "error": error_text.splitlines(),
            "exit_status": result.get("exit_status"),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
