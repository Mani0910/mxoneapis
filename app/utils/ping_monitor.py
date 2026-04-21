import subprocess
import time
import logging
import platform

logger = logging.getLogger(__name__)


def ping_host(host: str, timeout: int = 2) -> bool:
    """Ping a host and return True if reachable."""
    param = "-n" if platform.system().lower() == "windows" else "-c"
    timeout_param = "-w" if platform.system().lower() == "windows" else "-W"
    try:
        result = subprocess.run(
            ["ping", param, "1", timeout_param,
             str(timeout * 1000 if platform.system().lower() == "windows" else timeout), host],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout + 2
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception as e:
        logger.error(f"Ping error for {host}: {e}")
        return False


def monitor_reboot(
    host: str,
    reboot_timeout: int = 1800,
    ping_interval: int = 10,
    status_callback=None
) -> dict:
    """
    Monitor a host for reboot during upgrade using continuous ping.
    Phase 1: Wait for server to go DOWN (reboot started).
    Phase 2: Wait for server to come back UP (reboot completed).

    Args:
        host: IP or hostname to monitor
        reboot_timeout: Max seconds to wait for each phase
        ping_interval: Seconds between each ping
        status_callback: Optional callable(event, message) to report status

    Returns:
        dict with reboot status and timing info
    """
    def notify(event, message):
        logger.info(message)
        if status_callback:
            try:
                status_callback(event, message)
            except Exception:
                logger.exception("Status callback error in ping monitor")

    notify("ping_start", f"[PING] Starting continuous ping monitor for {host}")

    # -------------------------
    # Phase 1: Wait for DOWN
    # -------------------------
    down_start = time.time()
    server_went_down = False
    down_time = None

    while (time.time() - down_start) < reboot_timeout:
        if not ping_host(host):
            server_went_down = True
            down_time = time.time()
            elapsed = int(down_time - down_start)
            notify("rebooting", f"[PING] {host} is DOWN — server is rebooting (detected after {elapsed}s)")
            break
        notify("ping_up", f"[PING] {host} is still UP — waiting for reboot...")
        time.sleep(ping_interval)

    if not server_went_down:
        msg = f"[PING] {host} never went down within {reboot_timeout}s — reboot not detected"
        notify("ping_timeout", msg)
        return {
            "reboot_detected": False,
            "server_back_up": False,
            "message": msg,
            "downtime_seconds": 0
        }

    # -------------------------
    # Phase 2: Wait for UP
    # -------------------------
    up_start = time.time()
    server_came_up = False
    up_time = None

    while (time.time() - up_start) < reboot_timeout:
        if ping_host(host):
            up_time = time.time()
            server_came_up = True
            downtime = int(up_time - down_time)
            notify("ping_recovered", f"[PING] {host} is back UP — reboot completed (downtime: {downtime}s)")
            break
        notify("ping_down", f"[PING] {host} is still DOWN — reboot in progress...")
        time.sleep(ping_interval)

    if not server_came_up:
        total_down = int(time.time() - down_time)
        msg = f"[PING] {host} went down but did not come back up within {reboot_timeout}s"
        notify("ping_failed", msg)
        return {
            "reboot_detected": True,
            "server_back_up": False,
            "message": msg,
            "downtime_seconds": total_down
        }

    total_downtime = int(up_time - down_time)
    return {
        "reboot_detected": True,
        "server_back_up": True,
        "message": f"[PING] {host} rebooted and recovered successfully (downtime: {total_downtime}s)",
        "downtime_seconds": total_downtime
    }