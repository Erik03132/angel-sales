import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Эмуляция среды
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "agent"))

from call_learner import send_quality_alert

def test_alert():
    print("🚀 Тестирую отправку уведомлений ОКК...")
    
    # 1. Обычная проблема
    alert_warn = {
        "manager": "Марина Е",
        "phone": "+79781234567",
        "reason": "Менеджер не предложил апселл (петушки/корм), хотя клиент был готов купить.",
        "critical": False
    }
    
    # 2. Критический конфликт
    alert_crit = {
        "manager": "Эльзара",
        "phone": "+79997776655",
        "reason": "Критическое хамство: менеджер бросил трубку после фразы клиента 'почему так дорого'.",
        "critical": True
    }
    
    print("📤 Отправляю предупреждение...")
    send_quality_alert(alert_warn)
    
    print("📤 Отправляю критический аларм...")
    send_quality_alert(alert_crit)
    
    print("✅ Тест завершен. Проверьте Telegram!")

if __name__ == "__main__":
    test_alert()
