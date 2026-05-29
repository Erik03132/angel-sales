import os
from angelochka_core import get_answer

def verify_ptenchikova():
    # Симулируем окружение Песочницы
    os.environ["BITRIX_WEBHOOK_URL"] = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "https://b24-mjxvhq.bitrix24.ru/rest/1/...")
    
    print("\n🐣 ТЕСТ АНЖЕЛЫ ПТЕНЧИКОВОЙ (Песочница)")
    # Игорь спрашивает про дела
    ans = get_answer("Привет! Какие у нас сегодня задачи в песочнице?", sender_id="176203333")
    print(f"ОТВЕТ ПТЕНЧИКОВОЙ:\n{ans}")

def verify_zabotkina():
    # Симулируем окружение Продакшна
    os.environ["BITRIX_WEBHOOK_URL"] = os.getenv("PRODUCTION_BITRIX_WEBHOOK_URL", "https://incubird.bitrix24.ru/rest/...")
    
    print("\n🐥 ТЕСТ АНЖЕЛЫ ЗАБОТКИНОЙ (Продакшн)")
    # Игорь спрашивает про менеджеров
    ans = get_answer("Привет! Как там Марина и Эльзара работают?", sender_id="176203333")
    print(f"ОТВЕТ ЗАБОТКИНОЙ:\n{ans}")

if __name__ == "__main__":
    verify_ptenchikova()
    verify_zabotkina()
