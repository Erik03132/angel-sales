import os
import requests
import json
from dotenv import load_dotenv

# Загружаем ключи (BITRIX_WEBHOOK_URL)
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

BITRIX_WEBHOOK_URL = os.getenv("BITRIX_WEBHOOK_URL")

if not BITRIX_WEBHOOK_URL:
    raise ValueError("❌ BITRIX_WEBHOOK_URL не найден в .env")

# Сбрасываем слэш в конце, если есть, для удобства конкатенации
if BITRIX_WEBHOOK_URL.endswith('/'):
    BITRIX_WEBHOOK_URL = BITRIX_WEBHOOK_URL[:-1]

def fetch_bitrix_products():
    """
    Вытягивает всю номенклатуру (яйцо, цыплята, комбикорма) из Битрикс24.
    В CRM Азовского Инкубатора все цены, наличие и сроки должны лежать в товарах.
    """
    print(f"🔄 Стучимся в Битрикс24 по вебхуку...")
    url = f"{BITRIX_WEBHOOK_URL}/crm.product.list.json"
    
    # Настраиваем маску ответа (берем только нужные для RAG поля: Имя, Цена, Описание)
    payload = {
        "select": ["ID", "NAME", "PRICE", "CURRENCY_ID", "DESCRIPTION", "SECTION_ID", "PROPERTY_*", "QUANTITY"]
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        
        products = data.get("result", [])
        print(f"✅ Успешно получено {len(products)} товаров из Битрикс24.")
        
        return products
    
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка вызова Битрикс API: {e}")
        return []

def save_raw_nodes(products):
    """
    Сохраняет сырые продукты в виде JSON (PassageNodes).
    Далее этот файл будет препарироваться spaCy-парсером и векторизоваться.
    """
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
    os.makedirs(data_dir, exist_ok=True)
    filepath = os.path.join(data_dir, "raw_bitrix_products.json")
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
        
    print(f"💾 Сохранено в {filepath}")

if __name__ == "__main__":
    print("🚀 Старт Ingestion-модуля Анжелочки (Bitrix)")
    items = fetch_bitrix_products()
    if items:
        save_raw_nodes(items)
