import re
import socket
from paramiko.ssh_exception import AuthenticationException, NoValidConnectionsError, SSHException
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
            # Try direct and login-shell variants because non-interactive SSH
            # sessions may not have the MX-ONE binary in PATH.
            attempts = [
                "ts_about",
                "bash -lc 'ts_about'",
                "sh -lc 'ts_about'",
            ]
            result = {"output": "", "error": "", "exit_status": None}
            for command in attempts:
                candidate = execute_command(ssh, command)
                has_output = bool(candidate.get("output", "").strip())
                exit_ok = candidate.get("exit_status") == 0
                result = candidate
                if has_output or exit_ok:
                    break
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

        if not output_text.strip() and not error_text.strip():
            raise HTTPException(
                status_code=500,
                detail="ts_about returned no output. Verify PATH/permissions on target host.",
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
    except AuthenticationException:
        raise HTTPException(status_code=401, detail="SSH authentication failed.")
    except (NoValidConnectionsError, socket.timeout, TimeoutError):
        raise HTTPException(
            status_code=504,
            detail=(
                "Unable to reach target VM via SSH from this API server. "
                "If calling hosted Render endpoint, private/local IPs are not reachable."
            ),
        )
    except SSHException as e:
        raise HTTPException(status_code=500, detail=f"SSH error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
