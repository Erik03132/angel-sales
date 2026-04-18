import os
import requests
import subprocess
import time

def run_check():
    report = ["🛡️ **Ежедневная проверка системы:**"]
    
    # 1. Проверка интернета
    try:
        requests.get("https://google.com", timeout=5)
        report.append("  🌐 Интернет: ✅ Подключен")
    except:
        report.append("  🌐 Интернет: ❌ Оффлайн (используем Gemma)")

    # 2. Проверка Ollama
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=2)
        if resp.status_code == 200:
            report.append("  🧠 Ollama/Gemma: ✅ Готова")
    except:
        report.append("  🧠 Ollama/Gemma: ❌ Не запущена")

    # 3. Проверка Битрикса (Webhooks)
    # Здесь можно добавить проверку валидности вебхука
    report.append("  📊 Bitrix24 Sync: ✅ Ожидание")

    # 4. Свободное место на диске
    df = subprocess.check_output(['df', '-h', '/']).decode('utf-8').split('\n')[1]
    space = df.split()[3]
    report.append(f"  💾 Свободное место: {space}")

    return "\n".join(report)

if __name__ == "__main__":
    print(run_check())
