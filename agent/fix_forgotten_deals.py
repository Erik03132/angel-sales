#!/usr/bin/env python3
"""
1. Ответить Андрею в Битрикс — принять замечание
2. Пересчитать забытые сделки с правильными фильтрами
"""
import os, sys, json, requests
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "agent"))

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

from send_to_bitrix import send_bitrix_message

BITRIX_URL = os.getenv("BITRIX_WEBHOOK_URL", "").rstrip("/")

# === Стадии, которые НЕ являются забытыми ===
# Закрытые или завершённые стадии — их НЕ надо тревожить
CLOSED_STAGES = {
    "WON",          # Сделка успешна
    "LOSE",         # Клиент отказался
    "7",            # ДУБЛЬ заказа
    "APOLOGY",      # Мы отказали — нет товара
    "6",            # Отказ. Взял трубку при обзвоне
    "2",            # Отморозился
    "4",            # Недовоз по нашей вине
    "5",            # Причина неизвестна
    "10",           # Недоволен прошлой партией
    "12",           # Невозможно долго дозвониться
    "13",           # Не устраивает цена
}

# Стадии в процессе (сделка живая, менеджер работает)
ACTIVE_STAGES = {
    "UC_P1MPTA",    # Частично оплачен
    "EXECUTING",    # СМС заказ принят
    "9",            # Промежуточное СМС
    "3",            # СМС о доставке
    "11",           # Подтверждено
    "UC_FNNB7I",    # Подтверждение доставки
    "UC_44FPH8",    # Доставка подтверждена
}

# Только ЭТИ стадии реально "забытые" — клиент ждёт ответа
TRULY_FORGOTTEN_STAGES = {
    "NEW",          # Новый заказ — никто не позвонил
    "8",            # Ожидание предоплаты — нужно напомнить клиенту
}

print("=== ШАГИ ===")

# 1. Ответ Андрею в Битрикс
print("\n1. Отвечаем Андрею...")
reply = """Андрей, спасибо за замечание! Вы абсолютно правы.

Проверила: сделка #123408 - это ДУБЛЬ (стадия 'Дубль заказа'), а основной заказ идет на доставку 23.04. Менеджер все делает правильно.

Я допустила ошибку: считала 'забытыми' ВСЕ сделки без активности 3+ дня, включая:
- Дубли (стадия 7)
- Отказы (APOLOGY)
- Уже подтвержденные заказы (стадия 11)

Сейчас исправлюсь. Буду считать 'забытыми' ТОЛЬКО сделки на стадиях:
- 'Новый заказ' (NEW) - клиент оставил заявку, никто не перезвонил
- 'Ожидание предоплаты' (8) - нужно напомнить клиенту об оплате

Дубли, отказы и активные заказы больше трогать не буду. Простите за ложную тревогу!

- Анжелочка"""

result = send_bitrix_message(reply)
print(f"   Ответ отправлен: msg #{result}")

# 2. Пересчитываем забытые сделки
print("\n2. Загружаю сделки из JSON...")
with open(os.path.join(BASE_DIR, "data", "forgotten_deals.json"), "r", encoding="utf-8") as f:
    data = json.load(f)

old_count = len(data["deals"])
old_amount = sum(d["amount"] for d in data["deals"])

# Фильтруем: оставляем ТОЛЬКО действительно забытые
truly_forgotten = [d for d in data["deals"] if d.get("stage") in TRULY_FORGOTTEN_STAGES]
truly_forgotten.sort(key=lambda x: x["amount"], reverse=True)

new_count = len(truly_forgotten)
new_amount = sum(d["amount"] for d in truly_forgotten)

print(f"\n   БЫЛО: {old_count} сделок на {old_amount:,.0f} руб".replace(",", " "))
print(f"   СТАЛО: {new_count} сделок на {new_amount:,.0f} руб".replace(",", " "))
print(f"   УБРАНО: {old_count - new_count} ложных срабатываний")

# 3. По стадиям — что убрали
from collections import Counter
removed = [d for d in data["deals"] if d.get("stage") not in TRULY_FORGOTTEN_STAGES]
stage_counts = Counter(d.get("stage", "?") for d in removed)
print("\n   Убранные стадии:")
for stage, count in stage_counts.most_common():
    print(f"     {stage}: {count} сделок")

# 4. Сохраняем исправленный файл
data["deals"] = truly_forgotten
data["count"] = new_count
data["total_amount"] = new_amount
data["timestamp"] = datetime.now().isoformat()
data["fix_note"] = "v2: отфильтрованы дубли, отказы и активные стадии. Только NEW и 8."

# Пересчитываем по менеджерам
by_mgr = {}
for d in truly_forgotten:
    mgr = d["manager"]
    if mgr not in by_mgr:
        by_mgr[mgr] = {"count": 0, "total": 0}
    by_mgr[mgr]["count"] += 1
    by_mgr[mgr]["total"] += d["amount"]
data["by_manager"] = by_mgr

with open(os.path.join(BASE_DIR, "data", "forgotten_deals.json"), "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2, default=str)

print(f"\n   Файл forgotten_deals.json обновлен")
print(f"\n=== ГОТОВО ===")
