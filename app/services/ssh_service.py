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
        auth_timeout=30
    )
    return client



def execute_command(ssh, command: str):
    stdin, stdout, stderr = ssh.exec_command(command)

    return {
        "output": stdout.read().decode()
        
    }