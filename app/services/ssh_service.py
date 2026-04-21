import paramiko

def create_ssh_client(ip, username, password):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        ip,
        username=username,
        password=password,
        allow_agent=False,
        look_for_keys=False,
        auth_timeout=30,
        timeout=15,
        banner_timeout=15,
    )
    return client



def execute_command(ssh, command: str, timeout: int = 25):
    stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
    stdin.close()

    output = stdout.read().decode(errors="ignore")
    error = stderr.read().decode(errors="ignore")
    exit_status = stdout.channel.recv_exit_status()

    return {
        "output": output,
        "error": error,
        "exit_status": exit_status,
    }
