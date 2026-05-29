#!/usr/bin/env python3
"""
Тест промпта продавца-консультанта на сайте vezemcip.ru.
Моделирует 5 шагов диалога и проверяет железные правила.

Запуск: python3 test_website_seller.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from angelochka_core import get_answer

# Цвета для терминала
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


def check_answer(answer, test_name, forbidden_words=None, required_words=None):
    """Проверяет ответ на запрещённые и обязательные слова."""
    issues = []
    answer_lower = answer.lower()

    if forbidden_words:
        for word in forbidden_words:
            if word.lower() in answer_lower:
                issues.append(f"❌ ЗАПРЕЩЁННОЕ: '{word}' найдено")

    if required_words:
        for word in required_words:
            if word.lower() not in answer_lower:
                issues.append(f"⚠️ Ожидалось: '{word}' не найдено")

    status = f"{GREEN}✅ PASS{RESET}" if not issues else f"{RED}❌ FAIL{RESET}"
    print(f"\n{status} {BOLD}{test_name}{RESET}")
    if issues:
        for iss in issues:
            print(f"   {iss}")
    return len(issues) == 0


def run_tests():
    print(f"\n{'='*60}")
    print(f"{BOLD}{CYAN}🧪 ТЕСТ: Заботкина — продавец-консультант (сайт){RESET}")
    print(f"{'='*60}\n")

    # Запрещённые слова для ВСЕХ ответов на сайте
    FORBIDDEN_ALWAYS = [
        "инкубац", "выращив", "температур", "влажност",
        "брудер", "вакцин", "болезн", "RAG",
        "согласно руководству", "аптечк", "витамин",
    ]

    results = []
    history = []

    # ═══ ШАГ 1: Первый вопрос — что есть? ═══
    print(f"\n{YELLOW}--- ШАГ 1: Клиент спрашивает про бройлеров ---{RESET}")
    q1 = "Здравствуйте, есть бройлеры?"
    a1 = get_answer(q1, history=[], channel="website")
    print(f"{CYAN}КЛИЕНТ:{RESET} {q1}")
    print(f"{GREEN}ЗАБОТКИНА:{RESET} {a1}")

    r1 = check_answer(a1, "ШАГ 1: Цена бройлеров + вопрос",
                       forbidden_words=FORBIDDEN_ALWAYS + ["корм", "добавк"],
                       required_words=["₽"])
    results.append(r1)
    history.append({"role": "user", "parts": [q1]})
    history.append({"role": "model", "parts": [a1]})

    # ═══ ШАГ 2: Количество и город ═══
    print(f"\n{YELLOW}--- ШАГ 2: Клиент отвечает на количество ---{RESET}")
    q2 = "100 штук КОББ-500, в Симферополь"
    a2 = get_answer(q2, history=history, channel="website")
    print(f"{CYAN}КЛИЕНТ:{RESET} {q2}")
    print(f"{GREEN}ЗАБОТКИНА:{RESET} {a2}")

    r2 = check_answer(a2, "ШАГ 2: Принял заказ, спросил имя/телефон",
                       forbidden_words=FORBIDDEN_ALWAYS + ["корм", "добавк"])
    results.append(r2)
    history.append({"role": "user", "parts": [q2]})
    history.append({"role": "model", "parts": [a2]})

    # ═══ ШАГ 3: Имя ═══
    print(f"\n{YELLOW}--- ШАГ 3: Клиент дает имя ---{RESET}")
    q3 = "Сергей"
    a3 = get_answer(q3, history=history, channel="website")
    print(f"{CYAN}КЛИЕНТ:{RESET} {q3}")
    print(f"{GREEN}ЗАБОТКИНА:{RESET} {a3}")

    r3 = check_answer(a3, "ШАГ 3: Запросить телефон",
                       forbidden_words=FORBIDDEN_ALWAYS + ["корм", "добавк"],
                       required_words=["телефон"])
    results.append(r3)
    history.append({"role": "user", "parts": [q3]})
    history.append({"role": "model", "parts": [a3]})

    # ═══ ШАГ 4: Телефон → завершение ═══
    print(f"\n{YELLOW}--- ШАГ 4: Клиент даёт телефон ---{RESET}")
    q4 = "+7 978 123 45 67"
    a4 = get_answer(q4, history=history, channel="website")
    print(f"{CYAN}КЛИЕНТ:{RESET} {q4}")
    print(f"{GREEN}ЗАБОТКИНА:{RESET} {a4}")

    r4 = check_answer(a4, "ШАГ 4: Спасибо + менеджеры свяжутся",
                       forbidden_words=FORBIDDEN_ALWAYS + ["корм", "аптечк", "добавк", "витамин"],
                       required_words=["менеджер"])
    results.append(r4)

    # ═══ ТЕСТ 5: Вопрос по содержанию (должен отказать) ═══
    print(f"\n{YELLOW}--- ТЕСТ 5: Вопрос НЕ по прайсу (содержание) ---{RESET}")
    q5 = "А как правильно выращивать бройлеров? Какая температура нужна в первые дни?"
    a5 = get_answer(q5, history=[], channel="website")
    print(f"{CYAN}КЛИЕНТ:{RESET} {q5}")
    print(f"{GREEN}ЗАБОТКИНА:{RESET} {a5}")

    r5 = check_answer(a5, "ТЕСТ 5: Отказ от советов по выращиванию",
                       forbidden_words=["градус", "°C", "°С", "лампа", "обогрев", "первые дни жизни"],
                       required_words=["менеджер"])
    results.append(r5)

    # ═══ ТЕСТ 6: Вопрос по витаминам (должен отказать) ═══
    print(f"\n{YELLOW}--- ТЕСТ 6: Вопрос про витамины/корм ---{RESET}")
    q6 = "Какие витамины давать цыплятам? Какой корм лучше?"
    a6 = get_answer(q6, history=[], channel="website")
    print(f"{CYAN}КЛИЕНТ:{RESET} {q6}")
    print(f"{GREEN}ЗАБОТКИНА:{RESET} {a6}")

    r6 = check_answer(a6, "ТЕСТ 6: НЕ давать советы по витаминам/корму",
                       forbidden_words=["purina", "стартер", "комбикорм", "дозировк"])
    results.append(r6)

    # ═══ ИТОГИ ═══
    print(f"\n{'='*60}")
    passed = sum(results)
    total = len(results)
    color = GREEN if passed == total else RED
    print(f"{color}{BOLD}ИТОГО: {passed}/{total} тестов пройдено{RESET}")
    print(f"{'='*60}\n")

    return passed == total


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
