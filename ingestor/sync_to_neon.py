import os
import psycopg2
from psycopg2.extras import execute_values
from bitrix_parser import fetch_bitrix_products
from dotenv import load_dotenv

# 1. Загрузка настроек
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)
DATABASE_URL = os.getenv("NEON_DATABASE_URL")

def init_products_table(conn):
    """Создает таблицу продуктов, если её нет"""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                external_id TEXT UNIQUE,
                name TEXT NOT NULL,
                price NUMERIC,
                quantity INTEGER DEFAULT 0,
                stock_status TEXT,
                description TEXT,
                raw_properties JSONB,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
    print("✅ Таблица 'products' готова в Neon DB.")

def sync():
    if not DATABASE_URL:
        print("❌ Ошибка: NEON_DATABASE_URL не найден.")
        return

    # 1. Получаем данные из Битрикс
    bitrix_items = fetch_bitrix_products()
    if not bitrix_items:
        print("⚠️ Нет данных из Битрикс для синхронизации.")
        return

    # 2. Подключаемся к Neon
    conn = psycopg2.connect(DATABASE_URL)
    init_products_table(conn)

    # 3. Подготавливаем данные
    data_to_upsert = []
    for item in bitrix_items:
        # Пытаемся найти количество в QUANTITY или в одном из свойств (например PROPERTY_104)
        qty = 0
        try:
            qty = int(item.get("QUANTITY", 0))
            if not qty and "PROPERTY_104" in item:
                prop = item["PROPERTY_104"]
                qty = int(prop.get("value", 0)) if isinstance(prop, dict) else int(prop or 0)
        except:
            qty = 0

        stock = "В наличии" if (qty > 0 or float(item.get("PRICE", 0)) > 0) else "Под заказ"
        
        # Собираем все свойства для ИИ
        raw_props = {k: v for k, v in item.items() if k.startswith("PROPERTY_")}

        data_to_upsert.append((
            str(item["ID"]),
            item["NAME"],
            float(item.get("PRICE", 0)),
            qty,
            stock,
            item.get("DESCRIPTION", ""),
            psycopg2.extras.Json(raw_props)
        ))

    # 4. Выполняем UPSERT
    with conn.cursor() as cur:
        upsert_query = """
            INSERT INTO products (external_id, name, price, quantity, stock_status, description, raw_properties)
            VALUES %s
            ON CONFLICT (external_id) DO UPDATE SET
                name = EXCLUDED.name,
                price = EXCLUDED.price,
                quantity = EXCLUDED.quantity,
                stock_status = EXCLUDED.stock_status,
                description = EXCLUDED.description,
                raw_properties = EXCLUDED.raw_properties,
                updated_at = CURRENT_TIMESTAMP;
        """
        execute_values(cur, upsert_query, data_to_upsert)
        conn.commit()

    print(f"✨ Синхронизация завершена! Обработано товаров: {len(data_to_upsert)}")
    conn.close()

if __name__ == "__main__":
    sync()
