import threading
import time
from copy import deepcopy


_lock = threading.Lock()
_STATUS_TTL_SECONDS = 300  # keep completed/error status for 5 minutes

# Key: (ip, task)  e.g. ("10.1.1.1", "download") or ("10.1.1.1", "upgrade")
_store: dict = {}


def _default_progress(ip: str = "", task: str = ""):
    return {
        "task": task,
        "current_step": "",
        "state": "idle",
        "progress": 0,
        "message": "",
        "in_progress": 0,
        "target": ip,
    }


def _normalize(ip: str) -> str:
    return (ip or "").strip()


def _purge_expired_locked():
    now = time.time()
    expired = [k for k, v in _store.items()
               if v.get("completed_at") and now - v["completed_at"] >= _STATUS_TTL_SECONDS]
    for k in expired:
        del _store[k]


def begin_operation(ip: str, task: str, message: str = ""):
    """
    Atomically claim a (ip, task) slot.
    Returns (started: bool, current_state: dict).
    Two different tasks on the same IP are allowed in parallel.
    """
    key = (_normalize(ip), task)
    target = key[0] or "unknown"

    with _lock:
        _purge_expired_locked()
        current = _store.get(key)
        if current and current.get("in_progress") == 1:
            return False, deepcopy(current)

        payload = _default_progress(target, task)
        payload.update({
            "state": "in_progress",
            "message": message,
            "current_step": "start",
            "in_progress": 1,
        })
        _store[key] = payload
        return True, deepcopy(payload)


def update_progress(ip: str, patch: dict):
    """Update progress for a specific (ip, task) slot. task must be in the patch dict."""
    task = patch.get("task", "")
    key = (_normalize(ip) or "unknown", task)

    with _lock:
        _purge_expired_locked()
        current = _store.get(key)
        if not current:
            current = _default_progress(key[0], task)
            _store[key] = current

        current.update(patch)
        current["target"] = key[0]
        if current.get("state") in {"completed", "error"} and current.get("in_progress") == 0:
            current["completed_at"] = time.time()
        else:
            current.pop("completed_at", None)
        return deepcopy(current)


def get_progress(ip: str, task: str):
    """Get current status for a specific ip + task."""
    key = (_normalize(ip) or "unknown", task)
    with _lock:
        _purge_expired_locked()
        return deepcopy(_store.get(key, _default_progress(ip, task)))


def get_all_progress_by_task(task: str) -> dict:
    """Return {ip: status} for all IPs that have a record for this task."""
    with _lock:
        _purge_expired_locked()
        return {
            ip: deepcopy(v)
            for (ip, t), v in _store.items()
            if t == task
        }


def get_all_progress() -> dict:
    """Return everything keyed as 'ip::task'."""
    with _lock:
        _purge_expired_locked()
        return {f"{ip}::{task}": deepcopy(v) for (ip, task), v in _store.items()}
