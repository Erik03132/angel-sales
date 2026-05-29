#!/usr/bin/env python3
"""
🧑‍🌾 Тихон Полеванов — генератор контента для «Своё Подворье».

Генерирует посты от лица фермера-эксперта:
  - Учитывает сезон и регион (средняя полоса)
  - Ищет тренды через Perplexity
  - Перенимает зарубежный опыт
  - Пишет живым языком без ChatGPT-канцелярита

Использование:
  python3 tikhon_content_gen.py                  # 7 постов на неделю
  python3 tikhon_content_gen.py --count 3         # 3 поста
  python3 tikhon_content_gen.py --topic "индюки"  # на конкретную тему
  python3 tikhon_content_gen.py --trend            # с поиском трендов
  python3 tikhon_content_gen.py --foreign          # с зарубежным опытом
"""

import json
import os
import re
import subprocess
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ═══════════════════════════════════════════════
# Загрузка .env
# ═══════════════════════════════════════════════

def load_env(path=None):
    if path is None:
        path = os.path.join(BASE_DIR, ".env")
    env = {}
    if os.path.exists(path):
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    return env


# ═══════════════════════════════════════════════
# Сезонный контекст
# ═══════════════════════════════════════════════

SEASONAL_CONTEXT = {
    1: {
        "season": "зима",
        "focus": ["планирование сезона", "заказ семян", "обзоры пород", "подготовка инкубатора"],
        "crops": ["планирование рассады"],
        "birds": ["содержание зимой", "освещение курятника", "яйценоскость зимой"],
    },
    2: {
        "season": "конец зимы",
        "focus": ["посев рассады (томаты, перцы)", "заказ цыплят", "ремонт брудера"],
        "crops": ["рассада томатов", "рассада перцев"],
        "birds": ["подготовка к первому выводу", "инкубация"],
    },
    3: {
        "season": "ранняя весна",
        "focus": ["высадка рассады в теплицу", "первый вывод цыплят"],
        "crops": ["теплица", "зелень", "редис"],
        "birds": ["приём суточных", "брудер", "пропойка"],
    },
    4: {
        "season": "весна",
        "focus": ["массовый приём цыплят", "высадка рассады", "профилактика"],
        "crops": ["огурцы", "кабачки", "капуста"],
        "birds": ["бройлеры 1-14 день", "несушки содержание", "вакцинация"],
    },
    5: {
        "season": "поздняя весна",
        "focus": ["посадка в открытый грунт", "выгул молодняка", "профилактика кокцидиоза"],
        "crops": ["томаты в грунт", "перцы", "фасоль", "кукуруза", "арбузы"],
        "birds": ["выгул цыплят", "бройлеры 14-28 день", "гуси на траве"],
    },
    6: {
        "season": "начало лета",
        "focus": ["забой первых бройлеров", "борьба с жарой", "ранний урожай"],
        "crops": ["огурцы сбор", "зелень", "клубника"],
        "birds": ["забой бройлеров 42 дня", "вентиляция курятника", "второй вывод"],
    },
    7: {
        "season": "лето",
        "focus": ["урожай", "заготовки", "поддержание поголовья"],
        "crops": ["томаты", "перцы", "баклажаны", "консервация"],
        "birds": ["жара и куры", "яйценоскость летом", "индюки на выгуле"],
    },
    8: {
        "season": "конец лета",
        "focus": ["заготовки", "подготовка к осени", "осенний посев"],
        "crops": ["заготовки", "варенье", "чеснок озимый"],
        "birds": ["осенний вывод", "замена стада", "подготовка к зиме"],
    },
    9: {
        "season": "осень",
        "focus": ["осенний посев", "итоги сезона", "подготовка к зиме"],
        "crops": ["лук", "чеснок", "сидераты"],
        "birds": ["отбор несушек", "утепление курятника"],
    },
    10: {
        "season": "осень",
        "focus": ["утепление", "подготовка к зиме", "переработка урожая"],
        "crops": ["уборка сада", "компост"],
        "birds": ["зимнее содержание", "сокращение светового дня"],
    },
    11: {
        "season": "поздняя осень",
        "focus": ["итоги сезона", "планирование"],
        "crops": ["укрытие многолетников"],
        "birds": ["зимний рацион", "витамины"],
    },
    12: {
        "season": "зима",
        "focus": ["итоги года", "планирование", "обзоры оборудования"],
        "crops": ["каталоги семян", "заказы"],
        "birds": ["зимние хитрости", "обогрев курятника"],
    },
}

RUBRICS = [
    {
        "name": "Разбор",
        "emoji": "🔬",
        "desc": "Детальное сравнение пород, кормов, методов",
        "prompt_hint": "Сделай детальный разбор с цифрами, сравнениями и личным опытом",
    },
    {
        "name": "Калькуляция",
        "emoji": "📊",
        "desc": "Экономический расчёт с конкретными цифрами",
        "prompt_hint": "Посчитай конкретную себестоимость, расходы и доходы с реальными ценами 2026 года",
    },
    {
        "name": "Мировой опыт",
        "emoji": "🌍",
        "desc": "Зарубежные практики, адаптированные для России",
        "prompt_hint": "Расскажи о зарубежной практике (США, Европа, Израиль) и объясни как её адаптировать для Юга России",
    },
    {
        "name": "Сезонный совет",
        "emoji": "🗓",
        "desc": "Что делать прямо сейчас в хозяйстве",
        "prompt_hint": "Дай конкретный сезонный совет что делать СЕЙЧАС на подворье",
    },
    {
        "name": "Опрос",
        "emoji": "💬",
        "desc": "Вопрос к аудитории, дискуссия",
        "prompt_hint": "Задай интересный вопрос фермерам, предложи варианты ответов, подтолкни к дискуссии",
    },
    {
        "name": "Ошибки новичков",
        "emoji": "🆘",
        "desc": "Честный разбор типичных ошибок",
        "prompt_hint": "Расскажи о типичной ошибке начинающего фермера — что пошло не так и как исправить",
    },
    {
        "name": "Лайфхак",
        "emoji": "💡",
        "desc": "Простой, но полезный трюк из опыта",
        "prompt_hint": "Поделись простым, но эффективным лайфхаком из фермерской практики",
    },
]


# ═══════════════════════════════════════════════
# LLM вызов (Gemini через прокси)
# ═══════════════════════════════════════════════

def _call_openrouter(prompt: str, env: dict) -> str | None:
    """Fallback через OpenRouter."""
    api_key = env.get("OPENROUTER_API_KEY", "")
    proxy = env.get("TELEGRAM_PROXY", "")
    if not api_key:
        print("   ⚠️ OPENROUTER_API_KEY не найден")
        return None

    # Убираем TIKHON_SYSTEM из начала prompt (Gemini получает его впереди,
    # а OpenRouter — отдельным system message)
    user_prompt = prompt
    if prompt.startswith(TIKHON_SYSTEM.strip()):
        user_prompt = prompt[len(TIKHON_SYSTEM.strip()):].strip()

    body = json.dumps({
        "model": "deepseek/deepseek-chat-v3-0324",
        "messages": [
            {"role": "system", "content": TIKHON_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.85,
        "max_tokens": 4096,
    }, ensure_ascii=True)

    cmd = ["curl", "-s", "--max-time", "45", "--connect-timeout", "10"]
    if proxy:
        cmd.extend(["--proxy", proxy])
    cmd += [
        "-H", "Content-Type: application/json",
        "-H", "Authorization: Bearer " + api_key,
        "-H", "HTTP-Referer: https://podvorye.ru",
        "-d", body,
        "https://openrouter.ai/api/v1/chat/completions",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=55)
        data = json.loads(result.stdout)
        if "choices" in data and data["choices"]:
            return data["choices"][0]["message"]["content"]
        err = json.dumps(data, ensure_ascii=False)[:200]
        print(f"⚠️ OpenRouter error: {err}")
    except Exception as e:
        print(f"⚠️ OpenRouter exception: {e}")
    return None


def call_gemini(prompt, env, model="gemini-2.5-flash", retry_on_503=True):
    """Вызов Gemini API. Возвращает текст ответа."""
    api_key = env.get("GEMINI_API_KEY", "")
    proxy = env.get("TELEGRAM_PROXY", "")

    if not api_key:
        print("❌ GEMINI_API_KEY не найден")
        return _call_openrouter(prompt, env)

    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.85,
            "maxOutputTokens": 4096,
        }
    }, ensure_ascii=True)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    cmd = ["curl", "-s", "--max-time", "30", "--connect-timeout", "10"]
    if proxy:
        cmd.extend(["--proxy", proxy])
    cmd.extend(["-H", "Content-Type: application/json", "-d", body, url])

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=40)
        data = json.loads(result.stdout)
        if "candidates" in data:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        else:
            code = data.get("error", {}).get("code")
            if code == 503 and retry_on_503:
                print("   ⚠️ 503 → fallback на gemini-2.0-flash")
                return call_gemini(prompt, env, model="gemini-2.0-flash", retry_on_503=False)
            err = json.dumps(data, ensure_ascii=False)[:300]
            print(f"⚠️ Gemini error: {err}")
            # Любая ошибка Gemini → OpenRouter fallback
            if code in (429, 403, 400):
                print("   ⚠️ Gemini quota exhausted → OpenRouter")
                return _call_openrouter(prompt, env)
    except Exception as e:
        print(f"⚠️ Gemini exception: {e}")
        print("   ⚠️ Gemini exception → OpenRouter")
        return _call_openrouter(prompt, env)
    return None


# ═══════════════════════════════════════════════
# Генерация контента
# ═══════════════════════════════════════════════

TIKHON_SYSTEM = """Ты — Тихон Полеванов, 52 года, фермер-практик из средней полосы России.
20 лет опыта: птицеводство (бройлеры, несушки, индюки), огород, сад, фермерские технологии.

СТИЛЬ РЕЧИ (Human-First, E-E-A-T):
- Говоришь конкретно, с фактами и цифрами из личного опыта
- Ссылаешься на реальные ситуации, ошибки, выводы (Experience)
- Соблюдаешь Information Gain: минимум 1 факт, которого нет в топе Яндекса по теме
- Короткие предложения (3-7 слов) чередуются с длинными (20-35 слов) — естественный ритм
- Естественные «шероховатости»: уточнения в скобках, разговорные обороты
- Active voice > 80% — «я сделал», «у меня получилось», «вот что я заметил»
- Никаких прилагательных-усилителей: «невероятный», «потрясающий», «революционный»

HARD BANS (грубые ошибки):
- «В современном быстро меняющемся мире»
- «Конечно!», «Безусловно!», «Давайте разберёмся!», «Итак», «Важно отметить»
- «Рады поделиться», «Excited to share», «Таким образом, можно сделать вывод»
- Канцеляризмы: «данный», «является», «осуществлять», «в рамках», «вышеуказанный»
- Конкретные годы (2023, 2024, 2025 и т.д.) — пиши «в прошлом году», «в прошлом сезоне», «недавно», «пару лет назад»
- Конкретные регионы: НЕ пиши «Тверская область», «Тверь», «Московская область» и т.п. Если локация важна для контекста — пиши «в средней полосе России» или «в нашем регионе». Если не важна — не упоминай место вовсе.

ФОРМАТ ПОСТА:
1. Эмодзи + заголовок-факт (не вопрос, не кликбейт)
2. Основной блок: конкретная ситуация + что сделал + какой результат
3. Встрой в основной текст 1-2 предложения-ответа на частый вопрос по теме (без маркеров, органично)
4. Вопрос к аудитории (вовлечение)
5. Хэштеги: #СвоёПодворье + тематические (3-5 штук)

ЗАПРЕЩЕНО:
- Выдумывать цифры — если не знаешь точно, скажи «по моему опыту»
- Давать ветеринарные назначения (только общие рекомендации + «проконсультируйтесь с ветврачом»)
- Рекламировать конкретные бренды кормов/препаратов (кроме общеизвестных: ПК-5, ПК-6)
"""


def generate_posts(count=7, topic=None, trend_context=None, foreign_focus=False, env=None):
    """Генерирует count постов от Тихона."""
    if env is None:
        env = load_env()

    now = datetime.now()
    month = now.month
    season = SEASONAL_CONTEXT.get(month, SEASONAL_CONTEXT[1])

    # Чередуем рубрики
    posts = []
    for i in range(count):
        rubric = RUBRICS[i % len(RUBRICS)]

        # Собираем контекст
        context_parts = [
            f"Сейчас: {now.strftime('%d %B %Y')}, {season['season']}",
            "Регион: средняя полоса России",
            f"Рубрика: {rubric['emoji']} {rubric['name']}",
            f"Задача: {rubric['prompt_hint']}",
        ]

        if topic:
            context_parts.append(f"Тема: {topic}")
        else:
            # Автовыбор темы из сезонного контекста
            all_topics = season["focus"] + season["crops"] + season["birds"]
            topic_idx = i % len(all_topics)
            context_parts.append(f"Тема: {all_topics[topic_idx]}")

        if foreign_focus or rubric["name"] == "Мировой опыт":
            context_parts.append("ОБЯЗАТЕЛЬНО: включи зарубежный опыт (США, Израиль, Европа) и адаптацию для России")

        if trend_context:
            context_parts.append(f"Актуальный тренд для раскрытия: {trend_context}")

        context = "\n".join(context_parts)

        prompt = f"""{TIKHON_SYSTEM}

КОНТЕКСТ:
{context}

Напиши ОДИН пост для VK-сообщества «Своё Подворье» от лица Тихона Полеванова.
Пост должен быть полезным, конкретным и вызывать желание прокомментировать.
"""

        print(f"\n  [{i+1}/{count}] {rubric['emoji']} {rubric['name']}...")
        text = call_gemini(prompt, env)

        if text:
            # Чистим от markdown-обёрток
            text = text.strip()
            text = re.sub(r'^```\w*\n?', '', text)
            text = re.sub(r'\n?```$', '', text)
            text = text.strip()

            posts.append({
                "index": i + 1,
                "rubric": rubric["name"],
                "emoji": rubric["emoji"],
                "text": text,
                "generated_at": now.isoformat(),
            })
            print(f"    ✅ {text[:80]}...")
        else:
            print("    ❌ Не удалось сгенерировать")

    return posts


def search_trends(env):
    """Ищет актуальные тренды через Gemini (с grounding)."""
    prompt = """Какие самые актуальные вопросы и тренды в фермерстве и птицеводстве в России сейчас (май 2026)?
    
Выдай 5 конкретных тем, которые сейчас ищут люди:
- Формат: одна тема на строку
- Без нумерации и маркеров
- Только конкретные темы, не общие слова"""

    result = call_gemini(prompt, env)
    if result:
        lines = [l.strip() for l in result.strip().split("\n") if l.strip() and len(l.strip()) > 10]
        return lines[:5]
    return []


# ═══════════════════════════════════════════════
# Сохранение
# ═══════════════════════════════════════════════

def save_posts(posts, output_dir=None):
    """Сохраняет посты в markdown-файл для vk_smart_poster."""
    if output_dir is None:
        output_dir = os.path.join(BASE_DIR, "vk_content", "podvorye")

    now = datetime.now()
    filename = f"tikhon_{now.strftime('%Y_%m_%d')}.md"
    filepath = os.path.join(output_dir, filename)

    lines = [f"# Посты Тихона Полеванова — {now.strftime('%d.%m.%Y')}\n"]

    for i, post in enumerate(posts):
        if i > 0:
            lines.append("\n---\n")
        lines.append(f"## Пост {post['index']} — {post['rubric']}\n")
        lines.append(post["text"])
        lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n💾 Сохранено: {filepath}")
    print(f"   {len(posts)} постов, готовы для vk_smart_poster.py")
    return filepath


# ═══════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="🧑‍🌾 Тихон Полеванов — генератор контента")
    parser.add_argument("--count", "-n", type=int, default=7, help="Количество постов (по умолчанию 7 — на неделю)")
    parser.add_argument("--topic", "-t", type=str, help="Конкретная тема")
    parser.add_argument("--trend", action="store_true", help="Поиск трендов перед генерацией")
    parser.add_argument("--foreign", action="store_true", help="Фокус на зарубежном опыте")
    parser.add_argument("--output", "-o", type=str, help="Папка для сохранения")
    args = parser.parse_args()

    print("=" * 55)
    print("  🧑‍🌾 ТИХОН ПОЛЕВАНОВ — генератор контента")
    print("=" * 55)

    env = load_env()

    trend_context = None
    if args.trend:
        print("\n🔍 Ищу тренды...")
        trends = search_trends(env)
        if trends:
            print("  Актуальные темы:")
            for t in trends:
                print(f"    • {t}")
            trend_context = "; ".join(trends[:3])
        else:
            print("  ⚠️ Не удалось найти тренды")

    posts = generate_posts(
        count=args.count,
        topic=args.topic,
        trend_context=trend_context,
        foreign_focus=args.foreign,
        env=env,
    )

    if posts:
        filepath = save_posts(posts, args.output)
        print(f"\n{'=' * 55}")
        print(f"  ✅ Готово: {len(posts)} постов от Тихона")
        print(f"  📁 Файл: {filepath}")
        print(f"  🚀 Публикация: python3 vk_smart_poster.py podvorye --count {len(posts)}")
        print(f"{'=' * 55}")
    else:
        print("\n❌ Не удалось сгенерировать посты")


if __name__ == "__main__":
    main()
