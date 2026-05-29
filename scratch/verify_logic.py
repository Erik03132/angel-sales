import os
import sys
from datetime import datetime

# Настроим пути
BASE_DIR = "/Users/igorvasin/freelance-2026/ai-eggs"
sys.path.insert(0, os.path.join(BASE_DIR, "agent"))

from angelochka_core import _build_prompt_for_role

def verify_logic():
    print("--- ТЕСТ ЛОГИКИ ПЕРСОНАЖЕЙ (БЕЗ LLM) ---")
    
    # 1. Симулируем Песочницу Птенчиковой
    os.environ["BITRIX_WEBHOOK_URL"] = "https://b24-mjxvhq.bitrix24.ru/rest/1/..."
    prompt_p = _build_prompt_for_role("creator", "задачи", "", "", "", "")
    
    print("\n[ПРОМПТ ДЛЯ ПЕСОЧНИЦЫ]")
    if "Анжела Птенчикова" in prompt_p and "АКТУАЛЬНЫЕ ЗАДАЧИ В ПЕСОЧНИЦЕ" in prompt_p:
        print("✅ УСПЕХ: Птенчикова опознана, задачи из песочницы включены.")
    else:
        print("❌ ОШИБКА: Птенчикова или задачи не найдены в промпте.")
    
    # 2. Симулируем Продакшн Заботкиной
    os.environ["BITRIX_WEBHOOK_URL"] = "https://incubird.bitrix24.ru/rest/..."
    prompt_z = _build_prompt_for_role("creator", "менеджеры", "", "", "", "")
    
    print("\n[ПРОМПТ ДЛЯ ПРОДАКШНА]")
    if "Анжела Заботкина" in prompt_z and "СОТРУДНИКИ КОМПАНИИ" in prompt_z:
        print("✅ УСПЕХ: Заботкина опознана, отчет по менеджерам включен.")
    else:
        print("❌ ОШИБКА: Заботкина или отчет не найдены в промпте.")
        
    print(f"\nТекущая дата в системе: {datetime.now().strftime('%d.%m.%Y')}")
    if datetime.now().strftime('%d.%m.%Y') in prompt_p:
        print("✅ УСПЕХ: Текущая дата инжектирована в промпт.")

if __name__ == "__main__":
    verify_logic()
