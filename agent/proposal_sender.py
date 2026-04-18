"""
Отправка одного предложения в день из очереди.
Вызывается планировщиком в 20:00 после daily_report.
"""
import os
import json
from datetime import datetime
from send_to_bitrix import send_bitrix_message

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE_PATH = os.path.join(BASE_DIR, 'data', 'proposal_queue.json')


def send_next_proposal():
    """Отправляет следующее предложение из очереди."""
    if not os.path.exists(QUEUE_PATH):
        print("⚠️ Нет файла очереди предложений")
        return False
    
    with open(QUEUE_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    proposals = data.get("proposals", [])
    last_sent = data.get("meta", {}).get("last_sent_index", -1)
    
    # Находим следующее неотправленное
    next_proposal = None
    next_idx = None
    for i, p in enumerate(proposals):
        if p.get("status") == "pending":
            next_proposal = p
            next_idx = i
            break
    
    if not next_proposal:
        print("✅ Все предложения отправлены!")
        return False
    
    message = next_proposal.get("message", "")
    if not message:
        print(f"⚠️ Предложение #{next_proposal['id']} без текста")
        return False
    
    # Отправляем
    print(f"📨 Отправляю предложение: {next_proposal['title']}")
    result = send_bitrix_message(message)
    
    if result:
        # Обновляем статус
        proposals[next_idx]["status"] = "sent"
        proposals[next_idx]["sent"] = datetime.now().strftime("%Y-%m-%d")
        data["meta"]["last_sent_index"] = next_idx
        
        with open(QUEUE_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        remaining = sum(1 for p in proposals if p.get("status") == "pending")
        print(f"✅ Отправлено! Осталось: {remaining} предложений")
        return True
    else:
        print("⚠️ Ошибка отправки")
        return False


if __name__ == "__main__":
    send_next_proposal()
