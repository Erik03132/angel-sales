"""
🔌 AvitoMCP — Стандартный адаптер Avito API.

Ждём новые ключи от Андрея для полного функционала.
Пока: заглушки + готовая логика авторизации.
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)


class AvitoMCP:
    """МСР-адаптер для Avito REST API."""
    
    def __init__(self):
        self.client_id = os.getenv("AVITO_CLIENT_ID", "")
        self.client_secret = os.getenv("AVITO_CLIENT_SECRET", "")
        self.account_id = os.getenv("AVITO_ACCOUNT_ID", "71718357")
        self._token = None
        self._token_expires = 0
    
    def _auth(self) -> str:
        """Получить токен через client_credentials."""
        import time
        if self._token and time.time() < self._token_expires:
            return self._token
        
        try:
            resp = requests.post("https://api.avito.ru/token/", data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials"
            }, timeout=15)
            data = resp.json()
            if "access_token" in data:
                self._token = data["access_token"]
                self._token_expires = time.time() + data.get("expires_in", 3600) - 60
                return self._token
            else:
                print(f"⚠️ Avito auth error: {data.get('error', 'unknown')}")
        except Exception as e:
            print(f"⚠️ Avito auth exception: {e}")
        return ""
    
    def _api(self, method: str, endpoint: str, params=None, data=None) -> dict:
        """Вызов Avito API с авторизацией."""
        token = self._auth()
        if not token:
            return {"error": "No token"}
        
        headers = {"Authorization": f"Bearer {token}"}
        url = f"https://api.avito.ru/{endpoint}"
        
        try:
            if method == "GET":
                resp = requests.get(url, headers=headers, params=params, timeout=15)
            elif method == "POST":
                resp = requests.post(url, headers=headers, json=data, timeout=15)
            else:
                return {"error": f"Unknown method: {method}"}
            return resp.json()
        except Exception as e:
            return {"error": str(e)}
    
    @property
    def is_ready(self) -> bool:
        """Проверить работоспособность API."""
        token = self._auth()
        return bool(token)
    
    # --- ITEMS ---
    
    def get_items(self, status: str = "active", per_page: int = 100) -> list:
        """Получить объявления."""
        data = self._api("GET", f"core/v1/items", params={
            "per_page": per_page,
            "status": status
        })
        return data.get("resources", [])
    
    def get_item(self, item_id: int) -> dict:
        """Одно объявление."""
        return self._api("GET", f"core/v1/accounts/{self.account_id}/items/{item_id}")
    
    # --- STATS ---
    
    def get_stats(self, item_ids: list, date_from: str = None, date_to: str = None) -> list:
        """Статистика объявлений (просмотры, контакты, избранное)."""
        from datetime import datetime, timedelta
        if not date_from:
            date_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not date_to:
            date_to = datetime.now().strftime("%Y-%m-%d")
        
        data = self._api("POST", f"core/v1/accounts/{self.account_id}/stats/items", data={
            "dateFrom": date_from,
            "dateTo": date_to,
            "itemIds": item_ids,
            "fields": ["uniqViews", "uniqContacts", "uniqFavorites"]
        })
        return data.get("result", {}).get("items", [])
    
    # --- UPDATE ---
    
    def update_item(self, item_id: int, fields: dict) -> dict:
        """Обновить объявление (заголовок, описание, цену)."""
        return self._api("PUT", f"core/v1/accounts/{self.account_id}/items/{item_id}", data=fields)
