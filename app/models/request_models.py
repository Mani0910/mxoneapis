from pydantic import BaseModel, root_validator
from typing import Optional


class TransferRequest(BaseModel):
    ip: str
    username: str
    password: str
    build_name: str

class SSHCommandRequest(BaseModel):
    ip: str
    username: str
    password: str


class StatusRequest(BaseModel):
    ip: str
    username: str
    password: str


class DownloadRequest(BaseModel):
    """Download a build tag directly onto the target VM via SSH wget."""
    ip: str
    username: str
    password: str
    build_name: str          # build tag from /builds/list, e.g. mx7.6.sp1.hf0.rc19


class UpgradeRequest(BaseModel):
    host: str = ""           # resolved from ip if not provided
    ip: Optional[str] = None # alias for host; either host or ip must be set
    username: str
    password: str
    sudo_password: Optional[str] = ""  # defaults to password if blank
    version: str = ""        # 5-part dotted e.g. 7.6.1.0.19; auto-derived from build_name if omitted
    build_name: Optional[str] = None  # e.g. MX-ONE_7.8.sp0.hf0.rc23.bin; version derived from this

    @root_validator(pre=True)
    def normalize_upgrade_fields(cls, values):
        import re as _re
        # ip/host alias
        if not values.get("host"):
            values["host"] = values.get("ip") or ""
        if not values.get("ip"):
            values["ip"] = values.get("host") or ""
        # sudo_password defaults to password
        if not values.get("sudo_password"):
            values["sudo_password"] = values.get("password", "")
        # if version looks like a full filename, treat it as build_name
        _ver = values.get("version", "")
        if _ver and _ver.endswith(".bin"):
            if not values.get("build_name"):
                values["build_name"] = _ver
            values["version"] = ""

        # derive version from build_name if version not given
        if not values.get("version") and values.get("build_name"):
            m = _re.match(
                r"MX-ONE_(\d+)\.(\d+)\.sp(\d+)\.hf(\d+)\.rc(\d+)\.bin",
                values["build_name"],
            )
            if m:
                values["version"] = ".".join(m.groups())
        # normalise sp-style version "7.8.sp0.hf0.rc23" → "7.8.0.0.23"
        if values.get("version"):
            m = _re.match(
                r"(\d+)\.(\d+)\.sp(\d+)\.hf(\d+)\.rc(\d+)",
                values["version"],
            )
            if m:
                values["version"] = ".".join(m.groups())
        return values
