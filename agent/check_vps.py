import paramiko
import os
from dotenv import load_dotenv

# Загружаем доступы из .env
load_dotenv()

host = os.getenv("VPS_IP")
user = os.getenv("VPS_USER")
password = os.getenv("VPS_PASS")

def check_server():
    print(f"📡 Подключаюсь к {host}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(hostname=host, username=user, password=password, timeout=10)
        print("✅ Соединение установлено!")
        
        commands = [
            "uname -a",                  # Версия ядра/ОС
            "python3 --version",          # Версия Python
            "pip3 --version",             # Есть ли pip
            "ls -la /root/ai-eggs",       # Есть ли там уже папка проекта
            "free -h"                     # Сколько памяти (хватит ли на PyTorch)
        ]
        
        for cmd in commands:
            print(f"\n🚀 Выполняю: {cmd}")
            stdin, stdout, stderr = client.exec_command(cmd)
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            if out: print(f"OUT: {out}")
            if err: print(f"ERR: {err}")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    check_server()
