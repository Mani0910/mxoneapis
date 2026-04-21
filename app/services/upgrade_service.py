import logging
import threading
from copy import deepcopy

from app.services.upgrade_mxone import SystemUpgradeManager
from app.services.progress_store import progress_data

logging.basicConfig(level=logging.INFO)

_upgrade_lock = threading.Lock()


def _set_progress(state, progress, message, step, in_progress):
    progress_data.update({
        "task": "upgrade",
        "state": state,
        "progress": progress,
        "message": message,
        "current_step": step,
        "in_progress": in_progress,
    })


def _build_file_name(version):
    """
    Convert a 5-part version string to the MX-ONE build filename.
    "7.6.1.0.19"  →  "MX-ONE_7.6.sp1.hf0.rc19.bin"
    """
    parts = version.split('.')
    if len(parts) != 5:
        raise ValueError(
            f"version must be 5-part (e.g. 7.6.1.0.19), got: {version}"
        )
    major, minor, sp, hf, rc = parts
    return f"MX-ONE_{major}.{minor}.sp{sp}.hf{hf}.rc{rc}.bin"


def _run_upgrade_job(data):
    upgrader = None

    try:
        _set_progress("connecting", 0, "Connecting to server...", "connect", 1)

        def on_upgrade_event(event, message):
            if event == "rebooting":
                _set_progress("rebooting", -1, message, "reboot", 1)
            elif event == "recovered":
                _set_progress("in_progress", -1, message, "recovered", 1)
            elif event in ("ping_down", "ping_up", "ping_start"):
                _set_progress("rebooting", -1, message, "reboot_ping", 1)
            elif event == "ping_recovered":
                _set_progress("in_progress", -1, message, "reboot_ping_recovered", 1)
            elif event == "ping_failed":
                _set_progress("error", 0, message, "reboot_failed", 0)
            else:
                logging.info(f"[event:{event}] {message}")

        upgrader = SystemUpgradeManager(
            data.host,
            data.username,
            data.password,
            data.sudo_password,
            status_callback=on_upgrade_event,
        )
        upgrader.connect()

        build_file = _build_file_name(data.version)
        build_path = f"/local/home/mxone_admin/{build_file}"

        # -------------------------
        # DISTRIBUTE
        # -------------------------
        _set_progress("in_progress", 10, "Distributing build package", "distribute", 1)
        distribute_cmd = f"sh {build_path} --package_distribute"
        logging.info(f"Distribute command: {distribute_cmd}")
        upgrader.distribute_builds(distribute_cmd)

        # -------------------------
        # PREPARE
        # -------------------------
        _set_progress("in_progress", 30, "Preparing upgrade", "prepare", 1)
        prepare_cmd = (
            f'sh /opt/mxone_install/{data.version}/target/install_scripts/'
            f'sn_install_main.sh "upgrade_prepare" "" "" "silent"'
        )
        logging.info(f"Prepare command: {prepare_cmd}")

        try:
            upgrader.prepare_builds(prepare_cmd)
        except Exception as e:
            if "not allowed" in str(e).lower():
                logging.info("Prepare skipped (already done)")
            else:
                raise

        # -------------------------
        # SN UPGRADE
        # -------------------------
        _set_progress("in_progress", 50, "SN Upgrade in progress", "sn_upgrade", 1)
        upgrade_cmd = (
            f'sh /opt/mxone_install/{data.version}/target/install_scripts/'
            f'sn_install_main.sh "upgrade" "" "" "silent"'
        )
        logging.info(f"Upgrade command: {upgrade_cmd}")
        upgrader.perform_upgrade(upgrade_cmd)

        # -------------------------
        # SNM UPGRADE
        # -------------------------
        _set_progress("in_progress", 70, "SNM Upgrade in progress", "snm_upgrade", 1)
        snm_cmd = (
            f'sh /opt/mxone_install/{data.version}/addon_sw/'
            f'mxone_snm_install-{data.version}.bin'
        )
        logging.info(f"SNM command: {snm_cmd}")

        try:
            upgrader.perform_snm_upgrade(snm_cmd)
        except Exception as e:
            logging.warning(f"SNM upgrade issue: {e}")

        # -------------------------
        # PM UPGRADE
        # -------------------------
        _set_progress("in_progress", 85, "PM Upgrade in progress", "pm_upgrade", 1)
        pm_cmd = (
            f'sh /opt/mxone_install/{data.version}/addon_sw/'
            f'mxone_pm_install-{data.version}.bin'
        )
        logging.info(f"PM command: {pm_cmd}")

        try:
            upgrader.perform_pm_upgrade(pm_cmd)
        except Exception as e:
            if "not installed" in str(e).lower():
                logging.info("PM skipped (not installed)")
            else:
                raise

        # -------------------------
        # DONE
        # -------------------------
        _set_progress("completed", 100, "Upgrade completed successfully", "done", 0)

    except Exception as e:
        logging.exception("Upgrade failed")
        _set_progress("error", 0, str(e), "error", 0)

    finally:
        if upgrader:
            upgrader.disconnect()


def run_full_upgrade(data):
    with _upgrade_lock:
        if progress_data.get("in_progress") == 1:
            return {"status": "busy", "progress": deepcopy(progress_data)}

        threading.Thread(target=_run_upgrade_job, args=(data,), daemon=True).start()

        return {
            "status": "started",
            "message": f"Upgrade started for {data.host} to version {data.version}"
        }