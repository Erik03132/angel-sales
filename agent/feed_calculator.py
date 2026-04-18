"""
Калькулятор кормов и товарные наборы для Анжелочки.
Автоматический расчёт: порода + кол-во → корм + мешки + стоимость.
"""
import os
import re
import json
import math

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# Загрузка данных
_calc_data = {}
_calc_path = os.path.join(DATA_DIR, 'feed_calculator.json')
if os.path.exists(_calc_path):
    with open(_calc_path, 'r', encoding='utf-8') as f:
        _calc_data = json.load(f)
    print(f"✅ Feed Calculator загружен: {len(_calc_data.get('bundles', {}))} наборов")


def detect_feed_request(query: str) -> dict:
    """Определяет, содержит ли запрос вопрос про корм/расчёт.
    Возвращает {breed, count, bird_type} или None.
    """
    q = query.lower()
    
    # Определяем тип птицы
    breed_map = _calc_data.get("breed_to_type", {})
    detected_type = None
    detected_breed = None
    
    for breed_name, bird_type in breed_map.items():
        if breed_name.lower() in q:
            detected_type = bird_type
            detected_breed = breed_name
            break
    
    if not detected_type:
        return None
    
    # Ищем количество
    count_match = re.search(r'(\d+)\s*(шт|штук|голов|птиц|цыпл|утят|индюш|головы)?', q)
    count = int(count_match.group(1)) if count_match else None
    
    # Есть ли ключевые слова про корм/расчёт
    feed_keywords = ['корм', 'мешк', 'рассчит', 'посчит', 'сколько корм', 'нужно корм', 'кормить', 'кормлен', 'калькул']
    is_feed_question = any(kw in q for kw in feed_keywords)
    
    # Если найдена порода И (количество ИЛИ вопрос про корм) — считаем
    if is_feed_question or count:
        return {
            "breed": detected_breed,
            "bird_type": detected_type,
            "count": count
        }
    
    return None


def calculate_feed(bird_type: str, count: int) -> str:
    """Рассчитывает корм для указанного количества птицы."""
    norms = _calc_data.get("feed_norms", {}).get(bird_type)
    if not norms:
        return None
    
    total_kg = norms["total_kg_per_head"] * count
    phases = norms["phases"]
    
    lines = [f"🧮 РАСЧЁТ КОРМА на {count} голов ({bird_type}):\n"]
    
    total_cost = 0
    for phase in phases:
        days_count = phase["days"][1] - phase["days"][0] + 1
        phase_kg = (phase["daily_g"] * days_count * count) / 1000
        bags = math.ceil(phase_kg / 25)
        cost = bags * phase["price"]
        total_cost += cost
        lines.append(f"  📦 {phase['name']} (дни {phase['days'][0]}-{phase['days'][1]}): "
                     f"{phase_kg:.0f} кг → {bags} мешков × {phase['price']}₽ = {cost:,}₽".replace(",", " "))
    
    lines.append(f"\n  📊 ИТОГО: {total_kg:.0f} кг корма = {math.ceil(total_kg/25)} мешков")
    lines.append(f"  💰 Стоимость корма: ~{total_cost:,}₽".replace(",", " "))
    
    return "\n".join(lines)


def get_bundle_info(breed: str) -> str:
    """Возвращает товарный набор для породы."""
    bundles = _calc_data.get("bundles", {})
    
    # Ищем по точному или частичному совпадению
    bundle = None
    for bname, bdata in bundles.items():
        if bname.lower() in breed.lower() or breed.lower() in bname.lower():
            bundle = bdata
            breed = bname
            break
    
    if not bundle:
        return None
    
    lines = [f"📋 НАБОР для {breed}:\n"]
    lines.append(f"  🐣 Цена птенца: {bundle['bird_price']}₽")
    lines.append(f"  🌾 Корм: {', '.join(bundle['feed'])}")
    if bundle.get("extras"):
        lines.append(f"  💊 Допы: {', '.join(bundle['extras'])}")
    lines.append(f"\n  💡 {bundle['tip']}")
    
    return "\n".join(lines)


def process_feed_query(query: str) -> str:
    """Главная точка входа: определяет запрос и формирует ответ."""
    detection = detect_feed_request(query)
    if not detection:
        return None
    
    result_parts = []
    
    # Если есть количество — считаем корм
    if detection["count"]:
        calc = calculate_feed(detection["bird_type"], detection["count"])
        if calc:
            result_parts.append(calc)
        
        # Считаем стоимость птицы
        bundles = _calc_data.get("bundles", {})
        for bname, bdata in bundles.items():
            if bname.lower() in detection["breed"].lower() or detection["breed"].lower() in bname.lower():
                bird_cost = detection["count"] * bdata["bird_price"]
                result_parts.append(f"\n  🐣 Птица: {detection['count']} × {bdata['bird_price']}₽ = {bird_cost:,}₽".replace(",", " "))
                break
    
    # Добавляем набор
    bundle_info = get_bundle_info(detection["breed"])
    if bundle_info:
        result_parts.append(f"\n{bundle_info}")
    
    if result_parts:
        return "\n".join(result_parts)
    
    return None


if __name__ == "__main__":
    # Тесты
    tests = [
        "Сколько корма нужно на 100 бройлеров?",
        "Хочу 200 мулардов, посчитайте корм",
        "Рассчитайте корм на 50 индюков Биг-6",
    ]
    for q in tests:
        print(f"\n{'='*50}")
        print(f"Q: {q}")
        result = process_feed_query(q)
        print(result or "— Нет расчёта —")
