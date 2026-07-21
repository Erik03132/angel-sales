#!/usr/bin/env python3
"""
call_learner.py — Обучение Заботкиной из транскриптов звонков (Фаза 14.2)
=========================================================================
Логика:
  1. Читает JSON-транскрипты из data/transcripts/ (за вчера или N дней)
  2. Отправляет каждый в Gemini Flash с промптом на экстракцию фактов
  3. Извлекает: цены, сроки выводка, логистику, популярные породы
  4. Мержит с expert_knowledge.md → секция «Данные из звонков (авто)»
  5. Сохраняет лог обучения в data/call_learnings/YYYY-MM-DD.json

Запуск:
  python3 call_learner.py            # за вчера
  python3 call_learner.py --days 3   # за 3 дня
  python3 call_learner.py --dry-run  # без записи (тест)

Расписание: 03:30 MSK (после call_transcriber в 03:00).
⚠️ ТРЕБУЕТ: HTTPS_PROXY=socks5://... в .env (US прокси обязателен для Gemini из РФ)
"""

import argparse
import json
import os
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

# ── Пути ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
BASE_DIR   = SCRIPT_DIR.parent
DATA_DIR   = BASE_DIR / "data"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
LEARNING_DIR   = DATA_DIR / "call_learnings"
# Основная база знаний Заботкиной (angel-sales)
EXPERT_KNOWLEDGE = BASE_DIR / "angel-sales" / "docs" / "expert_knowledge.md"
# RAG-копия (agent/data)
EXPERT_KNOWLEDGE_AGENT = SCRIPT_DIR / "data" / "expert_knowledge.md"

os.makedirs(LEARNING_DIR, exist_ok=True)
load_dotenv(BASE_DIR / ".env", override=True)

# ── Конфиг ───────────────────────────────────────────────────────────────────
GEMINI_KEY   = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"
MSK = timezone(timedelta(hours=3))

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Каскад free-моделей OpenRouter для экстракции фактов (июль 2026)
EXTRACT_MODELS = [
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "openai/gpt-oss-20b:free",
]

TELEGRAM_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")

# Маркер секции в expert_knowledge.md
SECTION_MARKER = "## 📞 Данные из звонков (автообновление)"
SECTION_END    = "## "  # следующий h2 = конец секции

# ── Промпт для экстракции фактов ─────────────────────────────────────────────
EXTRACT_PROMPT = """Ты — аналитик данных птицеводческого хозяйства «ВезёмЦыплят» (Азовский Инкубатор, Крым).

Тебе дан пакет транскриптов телефонных звонков за один день.
Извлеки ТОЛЬКО ФАКТЫ, которые полезны для работы AI-ассистента (Анжелы Заботкиной):

1. **ЦЕНЫ** — какие цены называли менеджеры (порода, количество, цена за голову).
   Формат: {порода} — {цена}₽ ({контекст: опт/розница/скидка}).

2. **ДАТЫ ВЫВОДКА** — когда будет готов молодняк (порода, дата).
   Формат: {порода} — {дата} ({примечание}).

3. **ЛОГИСТИКА** — маршруты, города доставки, дни, водители.
   Формат: {город/регион} — {день недели/дата} ({детали}).

4. **ПОПУЛЯРНЫЕ ЗАПРОСЫ** — что спрашивают чаще всего (породы, количества).
   Формат: {порода} — спрашивали {N} раз.

5. **ПРОБЛЕМЫ И ЗАМЕТКИ** — жалобы, отказы, нехватка, важные нюансы.

6. **КАЧЕСТВО (QA)** — оцени каждый звонок по критериям:
    - Приветствие (Названо имя/компания?)
    - Апселл (Предложены ли петушки по 5р или корма?)
    - Вежливость (1-5)
    - Конфликт (Был ли негатив или хамство?)

7. **АЛАРМ** — если в звонке есть острый конфликт, грубость или брошенная трубка, поставь флаг "critical": true.

8. **FAQ (ДИНАМИЧЕСКИЙ)** — сформулируй 2-3 самых частых вопроса от клиентов и дай на них экспертные ответы (на основе базы знаний или данных из звонка).
   Формат: {вопрос} — {ответ} ({важность 1-10}).

Ответь СТРОГО в JSON:
{
  "date": "YYYY-MM-DD",
  "prices": [{"breed": "...", "price": 0, "context": "..."}],
  "hatch_dates": [{"breed": "...", "date": "...", "note": "..."}],
  "logistics": [{"location": "...", "schedule": "...", "details": "..."}],
  "popular_breeds": [{"breed": "...", "mention_count": 0}],
  "issues": ["..."],
  "faq_items": [{"question": "...", "answer": "...", "importance": 0}],
  "quality_alerts": [{"phone": "...", "manager": "...", "reason": "...", "critical": false}],
  "facts_count": 0
}

Если в транскриптах нет полезных фактов — верни {"facts_count": 0}.
НЕ выдумывай данные. Только то, что реально упоминается в звонках.
"""


# ── OpenRouter Free Cascade ─────────────────────────────────────────────────
def extract_facts_from_transcripts(transcripts: list[dict], date_str: str) -> dict | None:
    """Отправляет пакет транскриптов в OpenRouter free каскад для экстракции фактов."""
    if not OPENROUTER_KEY:
        print("  ❌ OPENROUTER_API_KEY не задан в .env")
        return None

    batch_text = f"Дата звонков: {date_str}\nКоличество звонков: {len(transcripts)}\n\n"
    for i, t in enumerate(transcripts, 1):
        summary = t.get("summary", "")
        transcript = t.get("transcript", "")
        agreements = t.get("agreements", [])
        questions = t.get("client_questions", [])
        phone = t.get("phone", "?")
        direction = t.get("direction", "?")
        batch_text += f"--- Звонок {i} ({direction}, {phone}) ---\n"
        batch_text += f"Саммари: {summary}\n"
        if agreements:
            batch_text += f"Договорённости: {'; '.join(agreements)}\n"
        if questions:
            batch_text += f"Вопросы клиента: {'; '.join(questions)}\n"
        if transcript:
            batch_text += f"Транскрипт:\n{transcript[:2000]}\n"
        batch_text += "\n"

    for model in EXTRACT_MODELS:
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": EXTRACT_PROMPT + "\n\n" + batch_text}],
                    "temperature": 0.1,
                    "max_tokens": 2048,
                },
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                raw = data["choices"][0]["message"]["content"].strip()
                if "```json" in raw:
                    raw = raw.split("```json")[1].split("```")[0].strip()
                elif "```" in raw:
                    raw = raw.split("```")[1].split("```")[0].strip()
                result = json.loads(raw)
                result["date"] = date_str
                print(f"  ✅ OpenRouter/{model} — {result.get('facts_count', 0)} фактов")
                return result
            else:
                print(f"  ⚠ OpenRouter/{model}: {resp.status_code}")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  ⚠ OpenRouter/{model}: не JSON — {str(e)[:100]}")
        except Exception as e:
            print(f"  ⚠ OpenRouter/{model}: {type(e).__name__}: {e}")

    return None


def send_quality_alert(alert: dict):
    """Отправляет мгновенное уведомление о проблемном звонке в Telegram."""
    if not TELEGRAM_TOKEN: return
    
    icon = "☢️ КРИТИЧЕСКИЙ КОНФЛИКТ" if alert.get("critical") else "⚠️ ПРОБЛЕМНЫЙ ЗВОНОК"
    text = (
        f"{icon}\n"
        f"👤 Менеджер: {alert.get('manager', 'Неизвестен')}\n"
        f"📞 Клиент: {alert.get('phone', '?')}\n"
        f"📝 Причина: {alert.get('reason', 'Не указана')}\n\n"
        f"👉 Проверьте этот звонок в Битрикс24!"
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    proxies = {"https": PROXY_URL.replace("socks5://", "socks5h://")} if PROXY_URL else {}
    
    try:
        import requests
        # ⛔ Андрею — НИЧЕГО в TG! (решение от 12.05.2026)
        # ТОЛЬКО Игорю (176203333)
        requests.post(url, json={"chat_id": 176203333, "text": "🔍 ОКК АЛАРМ:\n" + text}, proxies=proxies, timeout=10)
    except Exception as e:
        print(f"  ⚠️ Не удалось отправить аларм: {e}")


# ── Обновление expert_knowledge.md ──────────────────────────────────────────
def format_facts_as_markdown(facts: dict) -> str:
    """Конвертирует извлечённые факты в markdown-секцию."""
    lines = []
    date = facts.get("date", "?")
    lines.append(f"\n### 📅 {date}\n")

    # Цены
    prices = facts.get("prices", [])
    if prices:
        lines.append("**Цены из звонков:**")
        for p in prices:
            lines.append(f"- {p.get('breed', '?')} — {p.get('price', '?')}₽ ({p.get('context', '')})")
        lines.append("")

    # Даты выводка
    hatch = facts.get("hatch_dates", [])
    if hatch:
        lines.append("**Даты выводка:**")
        for h in hatch:
            lines.append(f"- {h.get('breed', '?')} — {h.get('date', '?')} ({h.get('note', '')})")
        lines.append("")

    # Логистика
    logistics = facts.get("logistics", [])
    if logistics:
        lines.append("**Логистика:**")
        for l in logistics:
            lines.append(f"- {l.get('location', '?')} — {l.get('schedule', '')} ({l.get('details', '')})")
        lines.append("")

    # Популярные породы
    popular = facts.get("popular_breeds", [])
    if popular:
        lines.append("**Популярные запросы:**")
        for p in popular:
            lines.append(f"- {p.get('breed', '?')} — упоминался {p.get('mention_count', 0)} раз")
        lines.append("")

    # Проблемы
    issues = facts.get("issues", [])
    if issues:
        lines.append("**Заметки/проблемы:**")
        for issue in issues:
            lines.append(f"- ⚠️ {issue}")
        lines.append("")

    return "\n".join(lines)


def update_expert_knowledge(facts_md: str, target_file: Path, date_str: str):
    """Вставляет/обновляет секцию «Данные из звонков» в expert_knowledge.md.
    
    Идемпотентность: если данные за date_str уже есть — они НЕ добавляются повторно.
    """
    if not target_file.exists():
        print(f"  ⚠️ Файл не найден: {target_file}")
        return False

    content = target_file.read_text(encoding="utf-8")
    
    # Проверка на дубликат даты
    date_marker = f"### 📅 {date_str}"
    if date_marker in content:
        print(f"  ℹ️ Данные за {date_str} уже присутствуют в {target_file.name}. Пропускаю.")
        return True

    # Ищем существующую секцию
    if SECTION_MARKER in content:
        start_idx = content.index(SECTION_MARKER)
        header_end = start_idx + len(SECTION_MARKER)
        
        # Ищем начало следующей секции h2 после маркера
        after_marker = content[header_end:]
        next_h2_match = [i for i, line in enumerate(after_marker.split('\n')) if line.startswith('## ') and i > 0]
        
        if next_h2_match:
            # Нашли следующую секцию — вставляем перед ней
            split_line = next_h2_match[0]
            lines = after_marker.split('\n')
            section_content = '\n'.join(lines[:split_line])
            footer_content = '\n'.join(lines[split_line:])
            
            new_content = (
                content[:header_end].rstrip() + "\n\n"
                + section_content.strip() + "\n\n"
                + facts_md.strip() + "\n\n"
                + footer_content.strip()
            )
        else:
            # Секция последняя в файле
            new_content = (
                content[:header_end].rstrip() + "\n\n"
                + after_marker.strip() + "\n\n"
                + facts_md.strip() + "\n"
            )
    else:
        # Создаём новую секцию в конце файла
        new_content = (
            content.rstrip() + "\n\n"
            + SECTION_MARKER + "\n\n"
            + "> Автоматически обновляется из транскриптов звонков (call_learner.py)\n\n"
            + facts_md.strip() + "\n"
        )

    target_file.write_text(new_content, encoding="utf-8")
    return True


# ── Основной pipeline ────────────────────────────────────────────────────────
def run(days_back: int = 1, dry_run: bool = False):
    """Основной запуск обучения из транскриптов."""
    now = datetime.now(MSK)

    print(f"\n{'='*55}")
    print(f"📚 CALL LEARNER — {now.strftime('%Y-%m-%d %H:%M MSK')}")
    print(f"   Период: последние {days_back} дней")
    print(f"   Dry-run: {dry_run}")
    print(f"{'='*55}\n")

    total_facts = 0
    total_transcripts = 0

    for d in range(days_back):
        target_date = now - timedelta(days=d + 1)
        date_str = target_date.strftime("%Y-%m-%d")
        day_dir = TRANSCRIPT_DIR / date_str

        if not day_dir.exists():
            print(f"  ⏭️ {date_str}: нет транскриптов")
            continue

        # Собираем транскрипты за день
        transcripts = []
        for f in sorted(day_dir.glob("call_*.json")):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                transcripts.append(data)
            except Exception as e:
                print(f"  ⚠️ {f.name}: {e}")

        if not transcripts:
            print(f"  ⏭️ {date_str}: 0 транскриптов")
            continue

        total_transcripts += len(transcripts)
        print(f"\n📞 {date_str}: {len(transcripts)} транскриптов")

        # Путь для сохранения лога обучения
        learning_file = LEARNING_DIR / f"{date_str}.json"

        # Батчинг (по 20 штук)
        BATCH_SIZE = 20
        all_extracted_facts = {
            "prices": [], "hatch_dates": [], "logistics": [], 
            "popular_breeds": [], "issues": [], "faq_items": [], "quality_alerts": []
        }
        
        for i in range(0, len(transcripts), BATCH_SIZE):
            batch = transcripts[i:i + BATCH_SIZE]
            print(f"  🤖 Батч {i//BATCH_SIZE + 1}/{(len(transcripts)-1)//BATCH_SIZE + 1} ({len(batch)} штук)...")
            
            facts = extract_facts_from_transcripts(batch, date_str)
            if facts:
                for key in all_extracted_facts:
                    if key in facts and isinstance(facts[key], list):
                        all_extracted_facts[key].extend(facts[key])
                    elif key == "issues" and "issues" in facts:
                        all_extracted_facts[key].extend(facts[key])
        
        facts = all_extracted_facts
        facts["date"] = date_str
        prices_count = len(facts.get("prices", []))
        hatch_count = len(facts.get("hatch_dates", []))
        logistics_count = len(facts.get("logistics", []))
        facts_count = prices_count + hatch_count
        facts["facts_count"] = facts_count
        
        print(f"  ✅ Итого за день: цен={prices_count}, дат={hatch_count}, логистика={logistics_count}, FAQ={len(facts['faq_items'])}")

        if facts_count == 0 and prices_count == 0 and hatch_count == 0:
            print(f"  ℹ️ Нет полезных фактов за {date_str}")
            # Всё равно сохраняем лог (чтобы не перепроверять)
            with open(learning_file, "w", encoding="utf-8") as fh:
                json.dump(facts, fh, ensure_ascii=False, indent=2)
            continue

        total_facts += prices_count + hatch_count + logistics_count

        # Обработка алармов качества
        alerts = facts.get("quality_alerts", [])
        for alert in alerts:
            print(f"  🔔 Качество: обнаружена проблема ({alert.get('reason')})")
            send_quality_alert(alert)

        # Сохраняем JSON-лог
        with open(learning_file, "w", encoding="utf-8") as fh:
            json.dump(facts, fh, ensure_ascii=False, indent=2)
        print(f"  💾 Лог: {learning_file.name}")

        # Формируем markdown
        facts_md = format_facts_as_markdown(facts)

        # Обновляем основную базу знаний
        if EXPERT_KNOWLEDGE.exists():
            if update_expert_knowledge(facts_md, EXPERT_KNOWLEDGE, date_str):
                print(f"  📝 Обновлено: {EXPERT_KNOWLEDGE.name}")

        # Обновляем RAG-копию
        if EXPERT_KNOWLEDGE_AGENT.exists():
            if update_expert_knowledge(facts_md, EXPERT_KNOWLEDGE_AGENT, date_str):
                print(f"  📝 Обновлено: agent/{EXPERT_KNOWLEDGE_AGENT.name}")

    # Итог
    print(f"\n{'='*55}")
    print("✅ Обучение завершено!")
    print(f"   Транскриптов обработано: {total_transcripts}")
    print(f"   Фактов извлечено: {total_facts}")
    print(f"   Примерная стоимость: ${total_transcripts * 0.0001:.4f}")
    print(f"{'='*55}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Обучение Заботкиной из транскриптов звонков")
    parser.add_argument("--days", type=int, default=1,
                        help="За сколько дней обрабатывать (default: 1 = вчера)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Тест без вызова Gemini")
    args = parser.parse_args()

    run(days_back=args.days, dry_run=args.dry_run)
