import threading
import threading
import time
from copy import deepcopy


_lock = threading.Lock()
_last_target = ""
_STATUS_TTL_SECONDS = 60


def _default_progress():
    return {
        "task": "",            # transfer | download | upgrade
        "current_step": "",    # current logical step name
        "state": "idle",       # idle | connecting | in_progress | rebooting | completed | error
        "progress": 0,           # 0-100 percent
        "message": "",          # human-readable status
        "in_progress": 0,        # 1 while operation is running
    }


def _purge_expired_locked():
    global _last_target

    now = time.time()
    expired_targets = []
    for target, status in _progress_by_target.items():
        completed_at = status.get("completed_at")
        if completed_at and now - completed_at >= _STATUS_TTL_SECONDS:
            expired_targets.append(target)

    for target in expired_targets:
        _progress_by_target.pop(target, None)
        if _last_target == target:
            _last_target = ""


_progress_by_target = {}


def _normalize_target(target: str) -> str:
    return (target or "").strip()


def begin_operation(target: str, task: str, message: str = ""):
    """
    Atomically start an operation on one target.
    Returns (started: bool, current_state: dict).
    """
    global _last_target

    key = _normalize_target(target)
    if not key:
        key = "unknown"

    with _lock:
        _purge_expired_locked()
        current = _progress_by_target.get(key)
        if current and current.get("in_progress") == 1:
            return False, deepcopy(current)

        payload = _default_progress()
        payload.update({
            "task": task,
            "state": "in_progress",
            "progress": 0,
            "message": message,
            "current_step": "start",
            "in_progress": 1,
            "target": key,
        })
        _progress_by_target[key] = payload
        _last_target = key
        return True, deepcopy(payload)


def update_progress(target: str, patch: dict):
    global _last_target

    key = _normalize_target(target)
    if not key:
        key = "unknown"

    with _lock:
        _purge_expired_locked()
        current = _progress_by_target.get(key)
        if not current:
            current = _default_progress()
            current["target"] = key
            _progress_by_target[key] = current

        current.update(patch)
        current["target"] = key
        if current.get("state") in {"completed", "error"} and current.get("in_progress") == 0:
            current["completed_at"] = time.time()
        else:
            current.pop("completed_at", None)
        _last_target = key
        return deepcopy(current)


def get_progress(target: str = ""):
    key = _normalize_target(target)
    with _lock:
        _purge_expired_locked()
        if key:
            return deepcopy(_progress_by_target.get(key, _default_progress()))

        if _last_target and _last_target in _progress_by_target:
            return deepcopy(_progress_by_target[_last_target])

        return deepcopy(_default_progress())


def get_all_progress():
    with _lock:
        _purge_expired_locked()
        return deepcopy(_progress_by_target)