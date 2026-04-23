import logging
import threading

from app.services.upgrade_mxone import SystemUpgradeManager
from app.services.progress_store import begin_operation, update_progress

logging.basicConfig(level=logging.INFO)


def _set_progress(target, state, progress, message, step, in_progress):
    update_progress(target, {
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


def _version_tuple(version):
    parts = version.split('.')
    if len(parts) != 5:
        raise ValueError(
            f"version must be 5-part (e.g. 7.6.1.0.19), got: {version}"
        )
    return tuple(int(part) for part in parts)


def _precheck_upgrade_request(data):
    """
    Validate current vs target version before starting background upgrade.
    Returns a dict response when the request should not start, else None.
    """
    upgrader = None
    target = data.host
    try:
        upgrader = SystemUpgradeManager(
            data.host,
            data.username,
            data.password,
            data.sudo_password,
        )
        upgrader.connect()
        current_version = upgrader.check_mxone_version()
        if not current_version:
            return None

        current_tuple = _version_tuple(current_version)
        target_tuple = _version_tuple(data.version)

        if current_tuple == target_tuple:
            update_progress(target, {
                "task": "upgrade",
                "state": "completed",
                "progress": 100,
                "message": (
                    f"Already on version {data.version}. You are already in the latest version."
                ),
                "current_step": "done",
                "in_progress": 0,
            })
            return {
                "status": "skipped",
                "message": (
                    f"Server {data.host} is already on version {data.version}. "
                    f"You are already in the latest version."
                ),
                "poll": f"GET /status/upgrade?ip={data.host}",
            }

        if target_tuple < current_tuple:
            update_progress(target, {
                "task": "upgrade",
                "state": "error",
                "progress": 0,
                "message": (
                    f"Target version {data.version} is older than current version {current_version}. "
                    f"Downgrade is not allowed. You are already on a newer version."
                ),
                "current_step": "version_check",
                "in_progress": 0,
            })
            return {
                "status": "rejected",
                "message": (
                    f"Target version {data.version} is older than current version {current_version}. "
                    f"Downgrade is not allowed. You are already on a newer version."
                ),
                "poll": f"GET /status/upgrade?ip={data.host}",
            }

        # -------------------------
        # CHECK BUILD FILE EXISTS ON VM
        # -------------------------
        build_file = _build_file_name(data.version)
        build_path = f"/local/home/mxone_admin/{build_file}"

        _, stdout, _ = upgrader.ssh_client.exec_command(
            f'test -f "{build_path}" && echo EXISTS || echo MISSING'
        )
        file_check = stdout.read().decode("utf-8", errors="ignore").strip()

        if file_check != "EXISTS":
            update_progress(target, {
                "task": "upgrade",
                "state": "error",
                "progress": 0,
                "message": (
                    f"Build file '{build_file}' not found on {data.host} "
                    f"at /local/home/mxone_admin/. "
                    f"Please run POST /builds/download first to transfer the build."
                ),
                "current_step": "file_check",
                "in_progress": 0,
            })
            return {
                "status": "rejected",
                "message": (
                    f"Build file '{build_file}' is not present on {data.host}. "
                    f"Please download it first using POST /builds/download."
                ),
                "build_file": build_file,
                "expected_path": build_path,
                "poll": f"GET /status/upgrade?ip={data.host}",
            }

        return None
    finally:
        if upgrader:
            try:
                upgrader.disconnect()
            except Exception:
                pass


def _run_upgrade_job(data):
    upgrader = None
    target = data.host

    try:
        _set_progress(target, "connecting", 0, "Connecting to server...", "connect", 1)

        def on_upgrade_event(event, message):
            if event == "rebooting":
                _set_progress(target, "rebooting", -1, message, "reboot", 1)
            elif event == "recovered":
                _set_progress(target, "in_progress", -1, message, "recovered", 1)
            elif event in ("ping_down", "ping_up", "ping_start"):
                _set_progress(target, "rebooting", -1, message, "reboot_ping", 1)
            elif event == "ping_recovered":
                _set_progress(target, "in_progress", -1, message, "reboot_ping_recovered", 1)
            elif event == "ping_failed":
                _set_progress(target, "error", 0, message, "reboot_failed", 0)
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
        # CHECK CURRENT VERSION
        # -------------------------
        _set_progress(target, "in_progress", 5, "Checking current installed version", "version_check", 1)
        current_version = upgrader.check_mxone_version()
        logging.info(f"Current: {current_version}  Target: {data.version}")

        if current_version and current_version == data.version:
            _set_progress(target, "completed", 100,
                          f"Already on version {data.version}, no upgrade needed",
                          "done", 0)
            return

        # -------------------------
        # CLEANUP OLDER VERSIONS
        # -------------------------
        _set_progress(target, "in_progress", 8, "Cleaning up older installed versions", "cleanup", 1)
        try:
            older = upgrader.get_older_versions()
            upgrader.delete_older_versions(older)
        except Exception as e:
            logging.warning(f"Cleanup step failed (non-fatal): {e}")

        # -------------------------
        # DISTRIBUTE
        # -------------------------
        _set_progress(target, "in_progress", 10, "Distributing build package", "distribute", 1)
        distribute_cmd = f"sh {build_path} --package_distribute"
        logging.info(f"Distribute command: {distribute_cmd}")
        upgrader.distribute_builds(distribute_cmd)

        # -------------------------
        # PREPARE
        # -------------------------
        _set_progress(target, "in_progress", 30, "Preparing upgrade", "prepare", 1)
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
        _set_progress(target, "in_progress", 50, "SN Upgrade in progress", "sn_upgrade", 1)
        upgrade_cmd = (
            f'sh /opt/mxone_install/{data.version}/target/install_scripts/'
            f'sn_install_main.sh "upgrade" "" "" "silent"'
        )
        logging.info(f"Upgrade command: {upgrade_cmd}")
        upgrader.perform_upgrade(upgrade_cmd)

        # -------------------------
        # SNM UPGRADE
        # -------------------------
        _set_progress(target, "in_progress", 70, "SNM Upgrade in progress", "snm_upgrade", 1)
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
        _set_progress(target, "in_progress", 85, "PM Upgrade in progress", "pm_upgrade", 1)
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
        _set_progress(target, "completed", 100, "Upgrade completed successfully", "done", 0)

    except Exception as e:
        logging.exception("Upgrade failed")
        _set_progress(target, "error", 0, str(e), "error", 0)

    finally:
        if upgrader:
            upgrader.disconnect()


def run_full_upgrade(data):
    started, current = begin_operation(
        data.host,
        "upgrade",
        f"Starting upgrade on {data.host}",
    )
    if not started:
        return {
            "status": "busy",
            "message": f"Another operation is already in progress on {data.host}.",
            "progress": current,
        }

    precheck_result = _precheck_upgrade_request(data)
    if precheck_result is not None:
        return precheck_result

    threading.Thread(target=_run_upgrade_job, args=(data,), daemon=True).start()

    return {
        "status": "started",
        "message": f"Upgrade started for {data.host} to version {data.version}",
        "poll": f"GET /status/upgrade?ip={data.host}",
    }