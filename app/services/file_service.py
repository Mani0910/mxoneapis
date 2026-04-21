from scp import SCPClient
import os
from app.config import BUILD_PATH, MXONE_REMOTE_DIR

def progress(filename, size, sent):
    percent = (sent / size) * 100
    print(f"{filename} → {percent:.2f}% ({sent}/{size} bytes)")

def transfer_file(ssh, build_name):
    local_path = os.path.join(BUILD_PATH, build_name)
    remote_path = f"{MXONE_REMOTE_DIR}/{build_name}"

    try:
        # Ensure remote directory exists
        ssh.exec_command(f"mkdir -p {MXONE_REMOTE_DIR}")

        scp = SCPClient(
            ssh.get_transport(),
            progress=progress   # 👈 important
        )

        scp.put(local_path, remote_path)
        scp.close()

        return remote_path

    except Exception as e:
        raise Exception(f"File Transfer Failed: {str(e)}")