"""
🔌 BitrixMCP — Стандартный адаптер Битрикс24 CRM.

Google AI Trend #2: Model Context Protocol — 
«a standardized, two-way connection for AI applications»

Единый интерфейс для всех агентов к CRM данным.
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)


class BitrixMCP:
    """МСР-адаптер для Битрикс24 REST API."""
    
    def __init__(self, webhook_url: str = None):
        self.url = (webhook_url or os.getenv("BITRIX_WEBHOOK_URL", "")).rstrip("/")
    
    def _call(self, method, params=None):
        try:
            resp = requests.get(f"{self.url}/{method}", params=params or {}, timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {}
    
    def _post(self, method, data=None):
        try:
            resp = requests.post(f"{self.url}/{method}", json=data or {}, timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {}
    
    # --- DEALS ---
    
    def get_deals(self, status=None, limit=50) -> list:
        """Получить сделки из CRM."""
        params = {"select[]": ["ID", "TITLE", "STAGE_ID", "OPPORTUNITY", 
                               "DATE_MODIFY", "CONTACT_ID", "ASSIGNED_BY_ID"],
                  "order[DATE_MODIFY]": "DESC"}
        if status:
            params["filter[STAGE_ID]"] = status
        data = self._call("crm.deal.list", params)
        return data.get("result", [])
    
    def get_deal(self, deal_id: int) -> dict:
        """Получить одну сделку по ID."""
        data = self._call("crm.deal.get", {"ID": deal_id})
        return data.get("result", {})
    
    def update_deal(self, deal_id: int, fields: dict) -> bool:
        """Обновить поля сделки."""
        data = self._post("crm.deal.update", {"ID": deal_id, "FIELDS": fields})
        return bool(data.get("result"))
    
    # --- CONTACTS ---
    
    def get_contacts(self, phone: str = None, limit=20) -> list:
        """Поиск контактов. Если phone — ищем по телефону."""
        params = {"select[]": ["ID", "NAME", "LAST_NAME", "PHONE", "EMAIL"],
                  "order[ID]": "DESC"}
        if phone:
            params["filter[PHONE]"] = phone
        data = self._call("crm.contact.list", params)
        return data.get("result", [])
    
    def get_contact(self, contact_id: int) -> dict:
        data = self._call("crm.contact.get", {"ID": contact_id})
        return data.get("result", {})
    
    # --- LEADS ---
    
    def create_lead(self, title: str, name: str = "", phone: str = "",
                    source: str = "AI_ANGELOCHKA", comment: str = "") -> int:
        """Создать лид в CRM."""
        fields = {
            "TITLE": title,
            "NAME": name,
            "SOURCE_ID": source,
            "COMMENTS": comment
        }
        if phone:
            fields["PHONE"] = [{"VALUE": phone, "VALUE_TYPE": "WORK"}]
        
        data = self._post("crm.lead.add", {"FIELDS": fields})
        return data.get("result", 0)
    
    # --- MESSAGING ---
    
    def send_message(self, dialog_id, text: str) -> int:
        """Отправить сообщение в мессенджер Битрикс."""
        if len(text) > 4000:
            text = text[:3900] + "\n\n... (обрезано)"
        data = self._post("im.message.add.json", {
            "DIALOG_ID": dialog_id,
            "MESSAGE": text
        })
        return data.get("result", 0)
    
    # --- USERS ---
    
    def get_user(self, user_id: int) -> dict:
        data = self._call("user.get", {"ID": user_id})
        users = data.get("result", [])
        return users[0] if users else {}
    
    def get_user_name(self, user_id: int) -> str:
        user = self.get_user(user_id)
        return f"{user.get('NAME', '')} {user.get('LAST_NAME', '')}".strip() or f"User#{user_id}"
