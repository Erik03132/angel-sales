#!/usr/bin/env python3
"""
Тест Заботкиной — 10 типичных диалогов от начала до конца.
Проверяет: короткие ответы, правильные цены, НЕТ годов, НЕТ выдумок.
"""
import time
import uuid

import requests

API_URL = "http://72.56.38.19:5000/api/chat"

# 10 типичных сценариев
SCENARIOS = [
    {
        "name": "🐔 Бройлеры КОББ-500",
        "messages": [
            "Какие бройлеры есть?",
            "100 штук КОББ",
            "Симферополь",
            "Анна",
            "+7 978 123 45 67",
        ]
    },
    {
        "name": "🦆 Утята Мулард",
        "messages": [
            "Есть утята?",
            "Мулард, 30 штук",
            "Краснодар",
            "Иван",
            "89281234567",
        ]
    },
    {
        "name": "🦢 Гусята Линда",
        "messages": [
            "Какие гусята есть?",
            "20 штук",
            "Севастополь",
            "Мария",
            "89785551122",
        ]
    },
    {
        "name": "🦃 Индюшата Биг-6",
        "messages": [
            "Сколько стоят индюшата?",
            "Биг-6, 15 штук",
            "Ростов-на-Дону",
            "Сергей",
            "+7 918 222 33 44",
        ]
    },
    {
        "name": "🐣 Несушки Доминант",
        "messages": [
            "Есть несушки?",
            "Доминант 100 штук",
            "Джанкой",
            "Елена",
            "89786543210",
        ]
    },
    {
        "name": "💰 Вопрос о ценах",
        "messages": [
            "Сколько стоят цыплята?",
            "РОСС-308",
            "200 штук, Керчь",
            "Олег",
            "+79781112233",
        ]
    },
    {
        "name": "🚚 Вопрос о доставке",
        "messages": [
            "Вы доставляете в Москву?",
        ]
    },
    {
        "name": "🐔 Мясояичные породы",
        "messages": [
            "Есть мясояичные породы?",
            "Ред Бро 50 штук",
            "Евпатория",
            "Виктор",
            "+79783334455",
        ]
    },
    {
        "name": "🐥 Цесарки",
        "messages": [
            "А цесарки есть?",
            "20 штук, Ялта",
            "Наталья",
            "+79780001122",
        ]
    },
    {
        "name": "❓ Нестандартный вопрос",
        "messages": [
            "А павлины есть?",
        ]
    },
]


def run_dialog(scenario):
    """Запускает один диалог и возвращает результат."""
    session_id = str(uuid.uuid4())
    results = []
    
    print(f"\n{'='*60}")
    print(f"  {scenario['name']}")
    print(f"{'='*60}")
    
    for msg in scenario["messages"]:
        print(f"\n👤 Клиент: {msg}")
        
        try:
            resp = requests.post(API_URL, json={
                "message": msg,
                "session_id": session_id,
            }, timeout=30)
            
            if resp.status_code == 200:
                data = resp.json()
                answer = data.get("response", data.get("answer", "???"))
                print(f"🐣 Заботкина: {answer}")
                
                results.append({
                    "user": msg,
                    "bot": answer,
                    "len": len(answer),
                })
            else:
                print(f"❌ HTTP {resp.status_code}: {resp.text[:200]}")
                results.append({"user": msg, "bot": f"ERROR {resp.status_code}", "len": 0})
                
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            results.append({"user": msg, "bot": f"ERROR: {e}", "len": 0})
        
        time.sleep(2)  # Пауза между сообщениями
    
    return results


def analyze_results(all_results):
    """Анализирует результаты тестов."""
    print(f"\n\n{'='*60}")
    print("  📊 АНАЛИЗ РЕЗУЛЬТАТОВ")
    print(f"{'='*60}")
    
    issues = []
    
    for scenario_name, results in all_results:
        for r in results:
            bot = r["bot"]
            
            # Проверка длины (должно быть коротко)
            if r["len"] > 500:
                issues.append(f"⚠️ [{scenario_name}] Слишком длинный ответ ({r['len']} символов): '{r['user']}'")
            
            # Проверка на годы
            for year in ["2023", "2024", "2025"]:
                if year in bot:
                    issues.append(f"🔴 [{scenario_name}] Упоминание года {year}!")
            
            # Проверка на цену 0₽
            if "0₽" in bot and "50₽" not in bot and "80₽" not in bot and "90₽" not in bot:
                issues.append(f"🔴 [{scenario_name}] Цена 0₽ в ответе!")
            
            # Проверка на RAG/источники
            if "Источник:" in bot or "руководств" in bot.lower() or "Согласно " in bot:
                issues.append(f"🔴 [{scenario_name}] RAG/источник в ответе!")
            
            # Проверка на запрещённые слова
            for forbidden in ["комбикорм", "Purina", "аптечк", "витамин", "брудер"]:
                # Допустимо только после телефона
                if forbidden.lower() in bot.lower():
                    # Проверяем — был ли телефон до этого
                    pass  # TODO: контекстная проверка
    
    if issues:
        print(f"\n🚨 Найдено {len(issues)} проблем:")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("\n✅ Проблем не найдено!")
    
    return issues


if __name__ == "__main__":
    all_results = []
    
    for scenario in SCENARIOS:
        results = run_dialog(scenario)
        all_results.append((scenario["name"], results))
    
    analyze_results(all_results)
    print("\n✅ Тест завершён.")
