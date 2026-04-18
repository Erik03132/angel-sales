#!/usr/bin/env python3
"""
Создание лида в Битрикс24 CRM из чата Анжелочки.
Использование:
  from bitrix_lead import create_lead
  lead_id = create_lead(name="Иван", phone="+7...", comment="Хочет 100 бройлеров")
"""
import os
import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

BITRIX_URL = os.getenv("BITRIX_WEBHOOK_URL", "").rstrip("/")


def create_lead(name: str, phone: str = "", email: str = "",
                comment: str = "", source: str = "WEB_CHAT"):
    """
    Создаёт лид в Bitrix24 CRM.
    
    Args:
        name: Имя клиента
        phone: Телефон (в любом формате)
        email: Email (если есть)
        comment: Комментарий (детали заявки, что хочет купить)
        source: Источник лида (WEB_CHAT, TELEGRAM и т.д.)
    
    Returns:
        dict: {"success": True, "lead_id": 123} или {"success": False, "error": "..."}
    """
    if not BITRIX_URL:
        return {"success": False, "error": "BITRIX_WEBHOOK_URL не задан в .env"}
    
    # Формируем поля лида
    fields = {
        "TITLE": f"🤖 Заявка с сайта: {name}",
        "NAME": name.split()[0] if name else "Посетитель",
        "COMMENTS": comment,
        "SOURCE_ID": "WEB",
        "SOURCE_DESCRIPTION": f"Чат-бот Анжелочка ({source})",
        "STATUS_ID": "NEW",
        "OPENED": "Y",
        "ASSIGNED_BY_ID": 1,  # Андрей
    }
    
    # Фамилия (если есть)
    name_parts = name.split()
    if len(name_parts) > 1:
        fields["LAST_NAME"] = " ".join(name_parts[1:])
    
    # Телефон
    if phone:
        fields["PHONE"] = [{"VALUE": phone, "VALUE_TYPE": "WORK"}]
    
    # Email
    if email:
        fields["EMAIL"] = [{"VALUE": email, "VALUE_TYPE": "WORK"}]
    
    try:
        resp = requests.post(
            f"{BITRIX_URL}/crm.lead.add.json",
            json={"fields": fields},
            timeout=15
        )
        data = resp.json()
        
        if resp.status_code == 200 and data.get("result"):
            lead_id = data["result"]
            print(f"✅ Лид создан в Битрикс24 (ID: {lead_id})")
            return {"success": True, "lead_id": lead_id}
        else:
            error = data.get("error_description", str(data))
            print(f"⚠️ Ошибка создания лида: {error}")
            return {"success": False, "error": error}
            
    except Exception as e:
        print(f"⚠️ Ошибка подключения к Битрикс: {e}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    # Тест
    result = create_lead(
        name="Тест Тестович",
        phone="+7-900-000-0000",
        comment="Тестовый лид из чата Анжелочки. Хочет 50 бройлеров КОББ-500."
    )
    print(result)
