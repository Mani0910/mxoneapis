from pydantic import BaseModel
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


class DownloadRequest(BaseModel):
    """Download a build from S3 directly onto the target VM via SSH wget."""
    ip: str
    username: str
    password: str
    sudo_password: Optional[str] = ""
    build_name: str          # e.g. MX-ONE_7.6.sp1.hf0.rc19.bin


class UpgradeRequest(BaseModel):
    host: str
    username: str
    password: str
    sudo_password: str
    version: str             # e.g. 7.6.1.0.19
