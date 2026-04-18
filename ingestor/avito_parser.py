import os
import requests
import json
from dotenv import load_dotenv

# Загружаем ключи
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

AVITO_CLIENT_ID = os.getenv("AVITO_CLIENT_ID")
AVITO_CLIENT_SECRET = os.getenv("AVITO_CLIENT_SECRET")

class AvitoParser:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = self._get_token()

    def _get_token(self):
        """Получаем временный токен доступа Avito API"""
        url = "https://api.avito.ru/token/"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        try:
            response = requests.post(url, data=payload)
            response.raise_for_status()
            return response.json().get("access_token")
        except Exception as e:
            print(f"❌ Ошибка получения токена Avito: {e}")
            return None

    def fetch_items(self):
        """Парсим объявления и их описания (это база знаний по товарам)"""
        if not self.access_token: return []
        
        print("📡 [Avito Parser]: Начинаю сбор объявлений...")
        url = "https://api.avito.ru/core/v1/items"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            items = response.json().get("resources", [])
            
            detailed_items = []
            for item in items:
                item_id = item["id"]
                # Тянем детали каждого объявления (текст, характеристики)
                detail_url = f"https://api.avito.ru/core/v1/items/{item_id}"
                detail_res = requests.get(detail_url, headers=headers)
                if detail_res.status_code == 200:
                    data = detail_res.json()
                    detailed_items.append({
                        "source": "avito",
                        "title": data.get("title"),
                        "description": data.get("description"),
                        "price": data.get("price"),
                        "address": data.get("address")
                    })
            
            return detailed_items
        except Exception as e:
            print(f"❌ Ошибка при парсинге Avito: {e}")
            return []

def save_avito_data(data):
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
    os.makedirs(data_dir, exist_ok=True)
    filepath = os.path.join(data_dir, "raw_avito_data.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 [Avito Parser]: Данные сохранены в {filepath}")

if __name__ == "__main__":
    if not AVITO_CLIENT_ID or not AVITO_CLIENT_SECRET:
        print("⚠️ Ошибка: AVITO ключи не найдены в .env")
    else:
        parser = AvitoParser(AVITO_CLIENT_ID, AVITO_CLIENT_SECRET)
        items = parser.fetch_items()
        if items:
            save_avito_data(items)
