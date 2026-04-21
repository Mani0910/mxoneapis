import paramiko
import time
import re
import logging
import threading
from typing import Callable, Optional
from app.utils.ping_monitor import monitor_reboot

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class SystemUpgradeManager:
    def __init__(self, hostname, username, password, sudo_password, port=22,
                 status_callback: Optional[Callable[[str, str], None]] = None):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.sudo_password = sudo_password
        self.port = port
        self.ssh_client = None
        self.status_callback = status_callback

    # -------------------------
    # SSH CONNECTION
    # -------------------------
    def connect(self):
        self.ssh_client = paramiko.SSHClient()
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh_client.connect(
            hostname=self.hostname,
            port=self.port,
            username=self.username,
            password=self.password,
        )
        logging.info(f"Connected to {self.hostname}")

    def disconnect(self):
        if self.ssh_client:
            self.ssh_client.close()
            logging.info("Disconnected")

    def _ensure_connected(self):
        if self.ssh_client is None:
            logging.info("--- SSH client is None, reconnecting ---")
            self.connect()

    def _notify_status(self, event, message):
        logging.info(f"[{event}] {message}")
        if self.status_callback:
            try:
                self.status_callback(event, message)
            except Exception:
                logging.exception("Status callback failed")

    # -------------------------
    # REBOOT HANDLING
    # -------------------------
    def _wait_for_host_after_reboot(self, timeout_seconds=1800, interval_seconds=15):
        ping_result = {}

        def run_ping_monitor():
            result = monitor_reboot(
                host=self.hostname,
                reboot_timeout=timeout_seconds,
                ping_interval=10,
                status_callback=self._notify_status
            )
            ping_result.update(result)

        ping_thread = threading.Thread(target=run_ping_monitor, daemon=True)
        ping_thread.start()

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            probe = paramiko.SSHClient()
            probe.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                probe.connect(
                    hostname=self.hostname,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    timeout=20,
                    banner_timeout=20,
                    auth_timeout=20,
                )
                probe.close()
                logging.info(f"[SSH] {self.hostname} is accessible — reboot complete")
                # Reconnect main ssh_client
                self.ssh_client = paramiko.SSHClient()
                self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                self.ssh_client.connect(
                    hostname=self.hostname,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                )
                ping_thread.join(timeout=5)
                return True
            except Exception:
                try:
                    probe.close()
                except Exception:
                    pass
                time.sleep(interval_seconds)

        ping_thread.join(timeout=5)
        return False

    # -------------------------
    # DISTRIBUTE
    # -------------------------
    def distribute_builds(self, distribute_command):
        logging.info(f"Distribute command: {distribute_command}")
        self._ensure_connected()

        shell = self.ssh_client.invoke_shell()
        shell.send('su -l root\n')
        time.sleep(2)
        shell.send(self.sudo_password + '\n')
        time.sleep(5)
        output = shell.recv(4096)
        logging.info("--- now sending distribute command ---")
        shell.send(distribute_command + '\n')

        while True:
            time.sleep(30)
            if shell.recv_ready():
                output = shell.recv(4096)
            else:
                logging.info("--- waiting for distribute command to complete ---")
                continue

            console_data = output.decode('utf-8', errors='ignore')

            if len(console_data) == 0:
                logging.info("--- Package distribution completed (EOF) ---")
                break

            if re.search('unpack failed', console_data):
                raise Exception('Unpack failed during distribute.')

            if re.search('not enough space on disk', console_data):
                raise Exception('Not enough space on disk during distribute.')

            if re.search('Enter number to select package', console_data):
                logging.info("--- Enter number to select package from, sending 1 ---")
                shell.send('1\n')

            if re.search('Type "yes" to abort other process', console_data):
                logging.info("--- typing yes to abort other process ---")
                shell.send('yes\n')

            if re.search(r'\(y/n\)', console_data):
                logging.info("--- (y/n) prompt, sending y ---")
                shell.send('y\n')

            if re.search('Enter bandwidth limit in Mbit', console_data):
                logging.info('--- sending 0 for bandwidth limit ---')
                shell.send('0\n')

            if re.search('Package distribute ready', console_data):
                logging.info("--- Package successfully distributed ---")
                break

            if re.search(r'[\$#]\s*$', console_data):
                logging.info("--- distribute completed (shell prompt) ---")
                break

            logging.info("--- waiting for distribute command to complete ---")

        time.sleep(30)
        logging.info("--- distribution of build is done successfully ---")
        self._notify_status("distribute_done", "Package distributed successfully")

    # -------------------------
    # PREPARE
    # -------------------------
    def prepare_builds(self, prepare_command):
        logging.info(f"Prepare command: {prepare_command}")
        self._ensure_connected()

        shell = self.ssh_client.invoke_shell()
        shell.send('su -l root\n')
        time.sleep(2)
        shell.send(self.sudo_password + '\n')
        time.sleep(5)
        shell.recv(4096)

        logging.info("--- now execute prepare command ---")
        shell.send(prepare_command + '\n')

        while True:
            time.sleep(30)
            if shell.recv_ready():
                output = shell.recv(4096)
            else:
                logging.info("--- waiting while prepare is being executed ---")
                continue

            console_data = output.decode('utf-8', errors='ignore')

            if len(console_data) == 0:
                logging.info("--- Prepare completed (EOF) ---")
                break

            if re.search('Type "yes" to abort other process', console_data):
                logging.info("--- typing yes to abort other process ---")
                shell.send('yes\n')

            if re.search('unpack failed', console_data):
                raise Exception('Unpack failed during prepare.')

            if re.search('not enough space on disk', console_data):
                raise Exception('Not enough space on disk during prepare.')

            if re.search('Prepare for upgrade failed', console_data):
                raise Exception('Prepare for upgrade failed.')

            if re.search('Upgrade prepare not allowed', console_data):
                logging.info("--- Prepare already executed, skipping ---")
                return

            if re.search('Timeout! No answer received from', console_data):
                logging.warning('--- Timeout during prepare ---')
                break

            if re.search('Prepare for upgrade ready', console_data):
                logging.info("--- Prepare for upgrade ready successfully ---")
                break

            if re.search(r'Ok to continue \(y/n\)', console_data) or re.search(r'\(y/n\)', console_data):
                logging.info("--- re-execution prompt, sending y ---")
                shell.send('y\n')

            if re.search(r'[\$#]\s*$', console_data):
                logging.info("--- prepare done (shell prompt) ---")
                break

            logging.info("--- waiting while prepare is being executed ---")

        time.sleep(30)
        logging.info("--- prepare is exiting now ---")
        self._notify_status("prepare_done", "Prepare completed successfully")

    # -------------------------
    # SN UPGRADE
    # -------------------------
    def perform_upgrade(self, upgrade_sn):
        logging.info(f"SN upgrade command: {upgrade_sn}")
        self._ensure_connected()

        shell = self.ssh_client.invoke_shell()
        shell.send('su -l root\n')
        time.sleep(2)
        shell.send(self.sudo_password + '\n')
        time.sleep(2)
        shell.recv(4096)

        logging.info("--- starting sn upgrade now ---")
        shell.send(upgrade_sn + '\n')
        time.sleep(60)

        reboot_detected = False
        for i in range(80):
            time.sleep(30)

            if shell.recv_ready():
                data = shell.recv(4096)
            else:
                logging.info("--- upgrade is in progress (no data) ---")
                continue

            console_data = data.decode('utf-8', errors='ignore')

            if len(console_data) == 0:
                logging.info("--- End of SN upgrade (EOF) ---")
                break

            if re.search('Type "yes" to abort other process', console_data):
                logging.info("--- typing yes to abort other process ---")
                shell.send('yes\n')

            if re.search(r'\(y/n\)', console_data):
                logging.info('--- (y/n) prompt, sending y ---')
                shell.send('y\n')

            if re.search('not enough space on disk', console_data):
                raise Exception('Not enough space on disk during SN upgrade.')

            if re.search('Prepare for upgrade failed', console_data):
                raise Exception('Prepare for upgrade failed during SN upgrade.')

            if re.search('Timeout! No answer received from', console_data):
                logging.warning('--- Timeout during SN upgrade ---')
                break

            # Reboot detection during SN upgrade
            reboot_patterns = [
                'system is going down for reboot',
                'rebooting',
                'closed by remote host',
                'connection reset by peer',
            ]
            lowered = console_data.lower()
            if (not reboot_detected) and any(p in lowered for p in reboot_patterns):
                reboot_detected = True
                self._notify_status("rebooting", f"Server rebooting during SN upgrade")
                if self._wait_for_host_after_reboot(timeout_seconds=1800):
                    self._notify_status("recovered", "Server back after reboot during SN upgrade")
                    return
                raise Exception("Server did not return after reboot during SN upgrade")

            if re.search('Finished', console_data) or re.search('successfully upgraded', console_data):
                logging.info("--- successfully upgraded ---")
                break

            if re.search('Prepare for upgrade ready', console_data):
                logging.info("--- SN upgrade done ---")
                break

            if re.search(r'[\$#]\s*$', console_data):
                logging.info("--- SN upgrade completed (shell prompt) ---")
                break

            logging.info("--- upgrade is in progress ---")

        time.sleep(30)
        logging.info("--- SN upgrade completed ---")
        self._notify_status("sn_done", "SN upgrade completed successfully")

    # -------------------------
    # PM UPGRADE (colocated)
    # Ported directly from working mxone/upgrade_mxone.py
    # -------------------------
    def perform_pm_upgrade(self, upgrade_pm_cmd):
        logging.info(f"PM upgrade command: {upgrade_pm_cmd}")
        self._ensure_connected()

        shell = self.ssh_client.invoke_shell()
        shell.send('su -l root\n')
        time.sleep(2)
        shell.send(self.sudo_password + '\n')
        time.sleep(2)

        ansi_escape = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -/]*[@-~]')

        logging.info("--- now run pm upgrade ---")
        shell.send(upgrade_pm_cmd + '\n')
        logging.info("--- waiting for upgrade to start ---")
        time.sleep(40)

        _upgradePM = True
        start_time = time.time()
        timeout = 3600  # 1 hour max
        data = b""

        while time.time() - start_time < timeout:
            time.sleep(60)

            if shell.recv_ready():
                data = shell.recv(4096)
            else:
                logging.info("--- No data received, waiting ---")
                time.sleep(30)
                continue

            console_data = data.decode('utf-8', errors='ignore')
            mxoneOutPut = ansi_escape.sub('', console_data).replace("\r\n", " ")

            if len(console_data) == 0:
                logging.info("--- PM upgrade EOF ---")
                break

            if re.search(r'\(y/n\)', mxoneOutPut):
                logging.info("--- sending y ---")
                shell.send('y\n')

            if re.search('Type "yes" to abort other process', mxoneOutPut):
                logging.info("--- typing yes to abort other process ---")
                shell.send('yes\n')

            if re.search('Enter bandwidth limit in Mbit', mxoneOutPut):
                shell.send('\n')

            if re.search('LICENSE AGREEMENT', mxoneOutPut):
                logging.info("--- LICENSE prompt, sending enter ---")
                shell.send('\n')

            if re.search('Do you want to proceed', mxoneOutPut):
                logging.info("--- Do you want to proceed, sending yes ---")
                shell.send('yes\n')

            if re.search('Do you want to continue', mxoneOutPut):
                logging.info("--- Do you want to continue, sending yes ---")
                shell.send('yes\n')

            if re.search('installed. Upgrade not possible', mxoneOutPut):
                logging.info("--- Already upgraded, skipping ---")
                break

            if re.search('is already installed', mxoneOutPut):
                logging.info("--- Already installed, skipping ---")
                break

            if re.search('Upgrade not possible', mxoneOutPut):
                logging.info("--- Upgrade not possible ---")
                shell.send('\n')
                _upgradePM = False
                break

            if re.search('ERROR: Database MP not found', mxoneOutPut):
                logging.info("--- ERROR: Database MP not found ---")
                _upgradePM = False
                break

            if re.search('System Setup Admin last name', mxoneOutPut):
                logging.info("--- ERROR: PM is not installed / No user present ---")
                break

            if re.search('System Setup Admin first name', mxoneOutPut):
                logging.info("--- ERROR: PM is not installed / No user present ---")
                break

            if re.search('Restart ordered', mxoneOutPut):
                logging.info('--- Successfully upgraded and ordered restart ---')
                time.sleep(120)
                _upgradePM = True
                break

            if re.search(r'Restart now\?', mxoneOutPut):
                shell.send('\n')
                logging.info('--- Restart now, sending enter ---')
                time.sleep(120)

            if re.search(r'Press enter key to close this dialogue', mxoneOutPut):
                shell.send('\n')
                logging.info('--- Closed dialogue window ---')
                time.sleep(60)

            if re.search(r'Press enter key to exit script', mxoneOutPut):
                logging.info('--- Exit script prompt ---')
                shell.send('\n')
                break

            if re.search('Timeout! No answer received from', mxoneOutPut):
                logging.warning('--- Timeout during PM upgrade ---')
                break

            logging.info("--- pm upgrade is in progress ---")

        # Restart jboss after PM upgrade
        logging.info("--- pm upgrade is done, restarting jboss ---")
        self._notify_status("pm_jboss_restart", "Restarting jboss after PM upgrade")

        try:
            shell.send("systemctl restart mxone_jboss.service\n")
            time.sleep(600)
            logging.info("--- jboss restarted successfully ---")
        except Exception as e:
            logging.warning(f"--- jboss restart via existing shell failed: {e}, trying fresh connection ---")
            try:
                self._ensure_connected()
                restart_shell = self.ssh_client.invoke_shell()
                restart_shell.send('su -l root\n')
                time.sleep(2)
                restart_shell.send(self.sudo_password + '\n')
                time.sleep(2)
                restart_shell.send("systemctl restart mxone_jboss.service\n")
                time.sleep(600)
                logging.info("--- jboss restarted successfully (fresh connection) ---")
            except Exception as e2:
                logging.error(f"--- Failed to restart jboss: {e2} ---")

        self._notify_status("pm_done", "PM upgrade completed")
        return _upgradePM

    # -------------------------
    # SNM UPGRADE
    # Uses same flow as PM upgrade
    # -------------------------
    def perform_snm_upgrade(self, upgrade_snm_cmd):
        logging.info(f"SNM upgrade command: {upgrade_snm_cmd}")
        self._ensure_connected()

        shell = self.ssh_client.invoke_shell()
        shell.send('su -l root\n')
        time.sleep(2)
        shell.send(self.sudo_password + '\n')
        time.sleep(2)

        ansi_escape = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -/]*[@-~]')

        logging.info("--- now run snm upgrade ---")
        shell.send(upgrade_snm_cmd + '\n')
        logging.info("--- waiting for SNM upgrade to start ---")
        time.sleep(40)

        start_time = time.time()
        timeout = 3600
        data = b""

        while time.time() - start_time < timeout:
            time.sleep(30)

            if shell.recv_ready():
                data = shell.recv(4096)
            else:
                logging.info("--- SNM: No data received, waiting ---")
                time.sleep(20)
                continue

            console_data = data.decode('utf-8', errors='ignore')
            mxoneOutPut = ansi_escape.sub('', console_data).replace("\r\n", " ")

            if len(console_data) == 0:
                logging.info("--- SNM upgrade EOF ---")
                break

            if re.search(r'\(y/n\)', mxoneOutPut):
                logging.info("--- SNM: sending y ---")
                shell.send('y\n')

            if re.search('Type "yes" to abort other process', mxoneOutPut):
                logging.info("--- SNM: typing yes ---")
                shell.send('yes\n')

            if re.search('LICENSE AGREEMENT', mxoneOutPut):
                logging.info("--- SNM: LICENSE prompt ---")
                shell.send('\n')

            if re.search('Do you want to proceed', mxoneOutPut):
                logging.info("--- SNM: proceed prompt ---")
                shell.send('yes\n')

            if re.search('Do you want to continue', mxoneOutPut):
                logging.info("--- SNM: continue prompt ---")
                shell.send('yes\n')

            if re.search('is already installed', mxoneOutPut):
                logging.info("--- SNM: Already installed, skipping ---")
                break

            if re.search('Upgrade not possible', mxoneOutPut):
                logging.info("--- SNM: Upgrade not possible ---")
                shell.send('\n')
                break

            if re.search('Restart ordered', mxoneOutPut):
                logging.info('--- SNM: Successfully upgraded, restart ordered ---')
                time.sleep(120)
                break

            if re.search(r'Restart now\?', mxoneOutPut):
                shell.send('\n')
                logging.info('--- SNM: Restart now ---')
                time.sleep(120)

            if re.search(r'Press enter key to close this dialogue', mxoneOutPut):
                shell.send('\n')
                logging.info('--- SNM: Closed dialogue ---')
                time.sleep(60)

            if re.search(r'Press enter key to exit script', mxoneOutPut):
                shell.send('\n')
                break

            if re.search('Timeout! No answer received from', mxoneOutPut):
                logging.warning('--- SNM: Timeout ---')
                break

            if re.search(r'[\$#]\s*$', mxoneOutPut):
                logging.info("--- SNM upgrade completed (shell prompt) ---")
                break

            logging.info("--- snm upgrade is in progress ---")

        logging.info("--- SNM upgrade completed ---")
        self._notify_status("snm_done", "SNM upgrade completed")
        return True