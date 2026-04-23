# services/build_service.py

import requests
from bs4 import BeautifulSoup
from config.config import BASE_URL

def get_builds_service():
    res = requests.get(BASE_URL)
    soup = BeautifulSoup(res.text, 'html.parser')

    builds = []

    for link in soup.find_all('a'):
        name = link.get_text().strip()
        if name.startswith("mx"):
            builds.append(name.rstrip('/'))

    return {
        "status": "success",
        "builds": builds
    }





import re
import threading
import requests
from bs4 import BeautifulSoup
import paramiko

from config.config import BASE_URL, DOWNLOAD_PATH
from utils.job_store import jobs

def download_worker(ip, data):
    state = jobs[ip]
    try:
        state["status"] = "running"

        build = data["build_name"]
        username = data["username"]
        password = data["password"]

        # Step 1: Find .bin file
        build_url = f"{BASE_URL}{build}/install/"
        res = requests.get(build_url)
        soup = BeautifulSoup(res.text, 'html.parser')

        bin_file = None
        for link in soup.find_all('a'):
            name = link.get_text().strip()
            if name.endswith(".bin"):
                bin_file = name
                break

        if not bin_file:
            state["status"] = "failed"
            state["error"] = "BIN file not found"
            return

        bin_url = build_url + bin_file
        state["file"] = bin_file

        # Step 2: SSH
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip, username=username, password=password)

        # Step 3: Download with progress tracking via wget bar output
        command = (
            f"mkdir -p {DOWNLOAD_PATH} && "
            f"wget --progress=bar:force:noscroll -O {DOWNLOAD_PATH}/{bin_file} {bin_url} 2>&1"
        )

        channel = ssh.get_transport().open_session()
        channel.set_combine_stderr(True)
        channel.exec_command(command)

        while not channel.exit_status_ready():
            if channel.recv_ready():
                chunk = channel.recv(4096).decode('utf-8', errors='ignore')
                matches = re.findall(r'(\d+)%', chunk)
                if matches:
                    state["progress"] = f"{matches[-1]}%"

        # Drain any remaining output
        while channel.recv_ready():
            chunk = channel.recv(4096).decode('utf-8', errors='ignore')
            matches = re.findall(r'(\d+)%', chunk)
            if matches:
                state["progress"] = f"{matches[-1]}%"

        exit_code = channel.recv_exit_status()
        ssh.close()

        if exit_code == 0:
            state["status"] = "completed"
            state["progress"] = "100%"
        else:
            state["status"] = "failed"
            state["error"] = "wget exited with non-zero status"

    except Exception as e:
        state["status"] = "failed"
        state["error"] = str(e)


def start_download_service(data):
    ip = data["ip"]

    jobs[ip] = {
        "status": "started",
        "progress": "0%"
    }

    thread = threading.Thread(target=download_worker, args=(ip, data))
    thread.start()

    return {"status": "started", "message": f"Download started for {ip}"}

    return {
        "status": "started",
        "job_id": job_id
    }