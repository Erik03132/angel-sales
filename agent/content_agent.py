#!/usr/bin/env python3
"""
✍️ CONTENT AGENT — Генерация контента для каналов продвижения.

Google AI Trend #1: «10x Marketing Manager — 
5 specialized agents working in parallel»

Возможности:
- Генерация заголовков для Авито (A/B тесты)
- Генерация постов VK/OK
- Генерация описаний объявлений
- Ответы на отзывы
- Сезонный контент

v1.0 — 15.04.2026
"""
import os
import sys
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

CONTENT_DIR = os.path.join(BASE_DIR, "data", "content")
os.makedirs(CONTENT_DIR, exist_ok=True)

# Загрузим knowledge base
_wisdom = ""
_wisdom_path = os.path.join(BASE_DIR, 'data', 'expert_knowledge.md')
if os.path.exists(_wisdom_path):
    with open(_wisdom_path, 'r', encoding='utf-8') as f:
        _wisdom = f.read()


def _call_llm(prompt: str) -> str:
    """Вызов LLM через каскад."""
    # Gemini
    if GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-2.0-flash")
            resp = model.generate_content(prompt)
            return resp.text
        except Exception:
            pass
    
    # OpenRouter
    if OPENROUTER_KEY:
        for model_name in ["google/gemini-2.0-flash-001", "google/gemini-2.0-flash-exp:free"]:
            try:
                resp = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
                    json={"model": model_name, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7},
                    timeout=20
                )
                data = resp.json()
                if "choices" in data:
                    return data["choices"][0]["message"]["content"]
            except Exception:
                pass
    
    return "❌ LLM недоступен"


# ============================================================
# 1. ЗАГОЛОВКИ АВИТО (A/B тесты)
# ============================================================
def generate_avito_titles(breed: str, price: int, count: int = 5) -> list:
    """Генерирует варианты заголовков для Авито.
    
    Args:
        breed: Порода (КОББ-500, РОСС-308, и т.д.)
        price: Цена за штуку
        count: Количество вариантов
    
    Returns:
        Список заголовков для A/B тестирования
    """
    prompt = f"""Ты — эксперт по объявлениям Авито в категории «Птицеводство».
Сгенерируй {count} вариантов заголовков для объявления.

Порода: {breed}
Цена: {price}₽ за штуку
Компания: Азовский инкубатор (Крым)

ПРАВИЛА:
- Максимум 50 символов (ограничение Авито)
- Используй цифры (цена, количество)
- Один заголовок с эмодзи, остальные без
- Один с упоминанием доставки
- Один с акцентом на качество/здоровье
- Формат: каждый заголовок на новой строке, без нумерации

ПРИМЕРЫ ХОРОШИХ ЗАГОЛОВКОВ:
- Цыплята КОББ-500 от 70₽ Доставка Крым
- Бройлер РОСС-308 здоровые крепкие от 85₽
- 🐣 Суточные цыплята КОББ-500 от фермы
"""
    result = _call_llm(prompt)
    titles = [line.strip() for line in result.strip().split("\n") if line.strip() and len(line.strip()) > 10]
    return titles[:count]


# ============================================================
# 2. ОПИСАНИЯ АВИТО
# ============================================================
def generate_avito_description(breed: str, price: int, details: dict = None) -> str:
    """Генерирует продающее описание для Авито."""
    details = details or {}
    prompt = f"""Ты — копирайтер для Авито-объявлений птицефермы.
Напиши продающее описание для объявления.

Порода: {breed}
Цена: {price}₽
Минимальный заказ: от 30 голов
Доставка: ПН и ЧТ по Крыму и Югу России, климат-контроль
Гарантия: 100% выживаемости при доставке
Адрес: пгт. Азовское, Джанкойский район, Крым

Дополнительно: {json.dumps(details, ensure_ascii=False) if details else 'нет'}

База знаний о породе:
{_wisdom[:2000]}

ПРАВИЛА:
- Максимум 2000 символов
- Начни с ГЛАВНОЙ выгоды (не с «Продаём...»)
- Укажи: порода, цена, мин.заказ, доставка, гарантия
- Добавь 2-3 совета по содержанию (покажи экспертность)
- Закончи призывом: «Звоните/пишите — забронируем!»
- Без шаблонных фраз типа «качественный товар»
- Используй 2-3 эмодзи
"""
    return _call_llm(prompt)


# ============================================================
# 3. ПОСТЫ VK/OK
# ============================================================
def generate_social_post(topic: str, platform: str = "vk") -> str:
    """Генерирует пост для соцсетей.
    
    Topics: 'season_start', 'new_breed', 'care_tips', 'promo', 'behind_scenes'
    """
    topic_descriptions = {
        "season_start": "Открытие сезона — весна, время заводить птенцов",
        "new_breed": "Появилась новая порода в ассортименте", 
        "care_tips": "Полезные советы по выращиванию птицы",
        "promo": "Акция или специальное предложение",
        "behind_scenes": "Закулисье фермы — как растут цыплята"
    }
    
    topic_desc = topic_descriptions.get(topic, topic)
    platform_name = "ВКонтакте" if platform == "vk" else "Одноклассники"
    
    prompt = f"""Ты — SMM-менеджер птицефермы «Азовский инкубатор» (Крым).  
Напиши пост для {platform_name}.

Тема: {topic_desc}

База знаний:
{_wisdom[:1500]}

ПРАВИЛА:
- Длина: 500-800 символов
- Стиль: живой, как от фермера, с юмором
- 3-5 хэштегов в конце
- 1-2 эмодзи
- Призыв к действию (комментарий, вопрос, или «пишите»)
- Для ОК: чуть более традиционный стиль
- Для VK: современный, можно молодёжный сленг 
"""
    return _call_llm(prompt)


# ============================================================
# 4. ОТВЕТЫ НА ОТЗЫВЫ
# ============================================================
def generate_review_reply(review_text: str, rating: int, platform: str = "avito") -> str:
    """Генерирует ответ на отзыв клиента."""
    sentiment = "положительный" if rating >= 4 else "нейтральный" if rating == 3 else "негативный"
    
    prompt = f"""Ты — Анжелочка, менеджер «Азовского инкубатора». 
Ответь на {sentiment} отзыв клиента на {platform}.

ОТЗЫВ (оценка {rating}/5):
«{review_text}»

ПРАВИЛА:
- Если позитивный: поблагодари, подчеркни экспертность
- Если негативный: извинись, предложи решение, покажи заботу
- Максимум 200 символов
- Обращайся по имени если указано
- Не используй шаблоны «Спасибо за отзыв»
- Подпись: Анжелочка, «Азовский инкубатор»
"""
    return _call_llm(prompt)


# ============================================================
# 5. BATCH ГЕНЕРАЦИЯ (для всего каталога)
# ============================================================
def generate_catalog_content(breeds: list = None) -> dict:
    """Генерирует контент для всего каталога пород.
    
    Returns:
        {"КОББ-500": {"titles": [...], "description": "..."}, ...}
    """
    if breeds is None:
        breeds = [
            {"name": "КОББ-500", "price": 90, "type": "бройлер"},
            {"name": "РОСС-308", "price": 85, "type": "бройлер"},
            {"name": "Мулард", "price": 280, "type": "утка"},
            {"name": "Линдовские", "price": 400, "type": "гусь"},
            {"name": "БИГ-6", "price": 450, "type": "индюк"},
            {"name": "Ломан Браун", "price": 250, "type": "несушка"},
        ]
    
    catalog = {}
    for breed in breeds:
        print(f"✍️ Генерирую контент для {breed['name']}...")
        
        titles = generate_avito_titles(breed["name"], breed["price"], count=3)
        description = generate_avito_description(breed["name"], breed["price"], 
                                                  {"type": breed.get("type", "")})
        
        catalog[breed["name"]] = {
            "titles": titles,
            "description": description,
            "generated": datetime.now().isoformat()
        }
    
    # Сохраняем
    output_path = os.path.join(CONTENT_DIR, f"catalog_content_{datetime.now().strftime('%Y%m%d')}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Каталог контента сохранён: {output_path}")
    
    # A2A: публикуем результат
    try:
        from a2a_protocol import report_insight
        report_insight("content_agent", f"Сгенерирован контент для {len(catalog)} пород", {
            "breeds": list(catalog.keys())
        })
    except Exception:
        pass
    
    return catalog


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Content Agent v1.0")
    parser.add_argument("--titles", type=str, help="Генерация заголовков для породы")
    parser.add_argument("--price", type=int, default=90, help="Цена")
    parser.add_argument("--post", type=str, help="Генерация поста (season_start|care_tips|promo)")
    parser.add_argument("--platform", type=str, default="vk", help="Платформа (vk|ok)")
    parser.add_argument("--catalog", action="store_true", help="Генерация контента для всего каталога")
    
    args = parser.parse_args()
    
    if args.titles:
        print(f"\n✍️ Заголовки для {args.titles} ({args.price}₽):\n")
        titles = generate_avito_titles(args.titles, args.price)
        for t in titles:
            print(f"  → {t}")
    
    elif args.post:
        print(f"\n✍️ Пост для {args.platform} ({args.post}):\n")
        post = generate_social_post(args.post, args.platform)
        print(post)
    
    elif args.catalog:
        print("\n✍️ Генерация каталога контента...\n")
        generate_catalog_content()
    
    else:
        # Демо: заголовки для КОББ-500
        print("\n✍️ DEMO: Заголовки для КОББ-500:\n")
        titles = generate_avito_titles("КОББ-500", 90, count=3)
        for t in titles:
            print(f"  → {t}")
        
        print("\n✍️ DEMO: Пост VK (сезон):\n")
        post = generate_social_post("season_start", "vk")
        print(post)
