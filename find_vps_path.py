import paramiko
import os

ip = "72.56.38.19"
user = "root"
password = "zE4qDJb-+Y+rv+"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    print(f"Connecting to {ip}...")
    client.connect(ip, username=user, password=password)
    print("Connected! Finding manage_angela.sh...")
    stdin, stdout, stderr = client.exec_command("find /root -name manage_angela.sh 2>/dev/null")
    paths = stdout.read().decode('utf-8').strip().split('\n')
    print("Found paths:", paths)
finally:
    client.close()
