import re
import requests
from bs4 import BeautifulSoup

from app.config import BASE_URL


def list_builds(installed_version: str = None):
    """
    Scrape MX-ONE build tags from the Gitea release tags page.
    If installed_version is provided (e.g. '7.6.1.0.19'), only return
    builds with a strictly higher version.
    """
    res = requests.get(BASE_URL, timeout=15)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")

    builds = []
    for link in soup.find_all("a"):
        name = link.get_text().strip().rstrip("/")
        if name.lower().startswith("mx"):
            builds.append(name)

    if installed_version:
        inst_tuple = _parse_version_str(installed_version)
        if inst_tuple:
            builds = [b for b in builds if _build_version(b) and _build_version(b) > inst_tuple]

    return builds


def get_build_bin_url(build_name: str):
    """
    Given a build tag name (e.g. mx7.6.sp1.hf0.rc19), find the .bin file
    under its /install/ directory and return (full_url, filename).
    Returns (None, None) if not found.
    """
    build_url = f"{BASE_URL}{build_name}/install/"
    res = requests.get(build_url, timeout=15)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    for link in soup.find_all("a"):
        name = link.get_text().strip()
        if name.endswith(".bin"):
            return build_url + name, name

    return None, None


def _build_version(tag_name: str):
    """Parse tag like mx7.6.sp1.hf0.rc19 → (7, 6, 1, 0, 19)."""
    m = re.match(r"mx(\d+)\.(\d+)\.sp(\d+)\.hf(\d+)\.rc(\d+)", tag_name, re.IGNORECASE)
    if m:
        return tuple(int(x) for x in m.groups())
    return None


def _parse_version_str(version_str: str):
    """Parse installed version like '7.6.1.0.19' → (7, 6, 1, 0, 19)."""
    parts = version_str.strip().split(".")
    padded = (parts + ["0"] * 5)[:5]
    try:
        return tuple(int(x) for x in padded)
    except ValueError:
        return None
