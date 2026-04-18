"""
Синхронизация товаров из Bitrix24 → angelochka_unified_brain.json
Обновляет каталог Анжелочки актуальными ценами и остатками.
"""
import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

BITRIX_URL = os.getenv("BITRIX_WEBHOOK_URL", "").rstrip("/")
BRAIN_PATH = os.path.join(BASE_DIR, 'data', 'angelochka_unified_brain.json')


def fetch_bitrix_products():
    """Загружает все товары из Bitrix24 CRM."""
    products = []
    start = 0
    while True:
        resp = requests.get(f"{BITRIX_URL}/crm.product.list.json", params={
            "start": start,
            "select[]": ["ID", "NAME", "PRICE", "CURRENCY_ID", "ACTIVE", "DESCRIPTION", "QUANTITY"]
        }, timeout=15)
        if resp.status_code != 200:
            break
        data = resp.json()
        products.extend(data.get("result", []))
        if data.get("next") is None:
            break
        start = data["next"]
    return products


def sync_products():
    """Синхронизирует товары Bitrix → brain."""
    print(f"📦 Загружаю товары из Bitrix24...")
    products = fetch_bitrix_products()
    print(f"   ✅ Получено {len(products)} товаров")

    # Загружаем текущий brain
    brain = []
    if os.path.exists(BRAIN_PATH):
        with open(BRAIN_PATH, 'r', encoding='utf-8') as f:
            brain = json.load(f)

    # Удаляем старые товары из brain
    brain = [item for item in brain if item.get("source") != "bitrix_crm"]
    
    # Добавляем свежие
    for p in products:
        if p.get("ACTIVE") == "Y":
            price = float(p.get("PRICE", 0) or 0)
            qty = p.get("QUANTITY", None)
            stock = f", в наличии: {qty} шт" if qty is not None else ""
            
            brain.append({
                "id": f"bitrix_{p['ID']}",
                "source": "bitrix_crm",
                "content": f"{p.get('NAME', '?')} — {price:.0f}₽{stock}",
                "metadata": {
                    "type": "product",
                    "bitrix_id": p["ID"],
                    "price": price,
                    "quantity": qty,
                    "synced_at": datetime.now().isoformat()
                }
            })

    # Сохраняем
    with open(BRAIN_PATH, 'w', encoding='utf-8') as f:
        json.dump(brain, f, ensure_ascii=False, indent=2)
    
    active = [p for p in products if p.get("ACTIVE") == "Y"]
    print(f"   ✅ Brain обновлён: {len(active)} активных товаров")
    print(f"   💾 Файл: {BRAIN_PATH}")
    
    return len(active)


if __name__ == "__main__":
    count = sync_products()
    print(f"\n✅ Синхронизация завершена. {count} товаров в brain.")
