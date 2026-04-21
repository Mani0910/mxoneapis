import re
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from app.config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_BUCKET, AWS_REGION


def _get_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )


def _parse_build_version(filename: str):
    """
    Parse build filename to a comparable 5-tuple.
    MX-ONE_7.6.sp1.hf0.rc19.bin  →  (7, 6, 1, 0, 19)
    """
    m = re.match(r"MX-ONE_(\d+)\.(\d+)\.sp(\d+)\.hf(\d+)\.rc(\d+)\.bin", filename)
    if m:
        return tuple(int(x) for x in m.groups())
    return None


def _installed_version_to_tuple(version_str: str):
    """
    Convert an installed version string to a comparable 5-tuple.
    Supports:
      "7.2"            → (7, 2, 0, 0, 0)
      "7.6.1.0.19"     → (7, 6, 1, 0, 19)
      "7.6.sp1.hf0.rc19" → (7, 6, 1, 0, 19)  (build-file style)
    """
    version_str = version_str.strip()

    # Try build-file style: major.minor.spX.hfY.rcZ
    m = re.match(r"(\d+)\.(\d+)\.sp(\d+)\.hf(\d+)\.rc(\d+)", version_str)
    if m:
        return tuple(int(x) for x in m.groups())

    # Try 5-part dotted: 7.6.1.0.19
    parts = version_str.split(".")
    padded = (parts + ["0"] * 5)[:5]
    try:
        return tuple(int(x) for x in padded)
    except ValueError:
        return None


def list_s3_builds(installed_version: str = None):
    """
    List all .bin builds in the S3 bucket.
    If installed_version is provided, only return builds with a higher version.
    Returns a list of dicts with name, size_bytes, size_gb, last_modified.
    """
    s3 = _get_s3_client()

    try:
        response = s3.list_objects_v2(Bucket=AWS_S3_BUCKET)
    except NoCredentialsError:
        raise Exception("AWS credentials are missing or invalid.")
    except ClientError as e:
        raise Exception(f"S3 error: {e.response['Error']['Message']}")

    inst_tuple = None
    if installed_version:
        inst_tuple = _installed_version_to_tuple(installed_version)

    builds = []
    for obj in response.get("Contents", []):
        key = obj["Key"]
        if not key.endswith(".bin"):
            continue

        ver_tuple = _parse_build_version(key)
        if inst_tuple and (ver_tuple is None or ver_tuple <= inst_tuple):
            continue

        size_bytes = obj["Size"]
        builds.append({
            "name": key,
            "size_bytes": size_bytes,
            "size_gb": round(size_bytes / (1024 ** 3), 2),
            "last_modified": obj["LastModified"].isoformat(),
            "_ver": ver_tuple,
        })

    # Sort ascending by version
    builds.sort(key=lambda b: b["_ver"] or (0,) * 5)

    # Remove internal sort key
    for b in builds:
        b.pop("_ver")

    return builds


def generate_presigned_url(key: str, expiry_seconds: int = 3600) -> str:
    """Generate a presigned GET URL for a given S3 object key."""
    s3 = _get_s3_client()
    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": AWS_S3_BUCKET, "Key": key},
            ExpiresIn=expiry_seconds,
        )
        return url
    except ClientError as e:
        raise Exception(f"Failed to generate presigned URL: {e.response['Error']['Message']}")
