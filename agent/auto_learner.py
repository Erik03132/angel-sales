"""
Авто-обучение Анжелочки на реальных диалогах.
Анализирует логи: если клиент оставил телефон → диалог успешный.
Извлекает паттерны и обновляет FAQ + SKILL.

Механизм:
1. Парсит traces.json и историю бота
2. Находит диалоги с конверсией (телефон собран)
3. Извлекает лучшие Q&A пары
4. Добавляет в faq_drafts.json (черновики, требуют модерации)
"""
import os
import re
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
TRACES_PATH = os.path.join(DATA_DIR, 'traces.json')
FAQ_DRAFTS_PATH = os.path.join(DATA_DIR, 'faq_drafts.json')
FAQ_CACHE_PATH = os.path.join(DATA_DIR, 'faq_cache.json')
LEARNING_LOG_PATH = os.path.join(DATA_DIR, 'learning_log.json')

# Паттерн телефона (РФ)
PHONE_PATTERN = re.compile(r'(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}')


def load_json(path, default=None):
    if default is None:
        default = {}
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def detect_conversion(text):
    """Определяет, содержит ли текст телефон (конверсия)."""
    return bool(PHONE_PATTERN.search(text))


def extract_successful_patterns(traces):
    """Извлекает Q&A пары из успешных (с конверсией) диалогов."""
    successful = []
    
    for i, trace in enumerate(traces):
        query = trace.get("query", "")
        answer = trace.get("answer_preview", "")
        
        # Диалог успешен, если:
        # 1. В предыдущих или следующих traces есть телефон
        # 2. Качество контекста высокое
        # 3. Ответ достаточно длинный (= информативный)
        
        is_conversion = False
        
        # Проверяем соседние traces (±3) на наличие телефона
        for j in range(max(0, i-3), min(len(traces), i+4)):
            q = traces[j].get("query", "")
            a = traces[j].get("answer_preview", "")
            if detect_conversion(q) or detect_conversion(a):
                is_conversion = True
                break
        
        if is_conversion and len(answer) > 50:
            # Нормализуем вопрос
            q_clean = query.strip().lower()
            if len(q_clean) > 5:  # Слишком короткие — мусор
                successful.append({
                    "question": q_clean,
                    "answer": answer,
                    "quality": trace.get("context_quality", "unknown"),
                    "timestamp": trace.get("iso_time", ""),
                    "source": "auto_learning"
                })
    
    return successful


def deduplicate_drafts(drafts, existing_faq):
    """Убирает дубли: если вопрос уже в FAQ — не добавляем."""
    existing_keys = set(k.lower() for k in existing_faq.keys())
    unique = []
    seen = set()
    
    for draft in drafts:
        q = draft["question"]
        if q not in existing_keys and q not in seen:
            unique.append(draft)
            seen.add(q)
    
    return unique


def run_learning():
    """Главный процесс обучения."""
    print(f"\n{'='*50}")
    print(f"🧠 АВТО-ОБУЧЕНИЕ — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    # 1. Загружаем данные
    traces = load_json(TRACES_PATH, default=[])
    existing_faq = load_json(FAQ_CACHE_PATH)
    existing_drafts = load_json(FAQ_DRAFTS_PATH, default=[])
    
    print(f"📊 Traces: {len(traces)} записей")
    print(f"📚 FAQ: {len(existing_faq)} записей")
    print(f"📝 Черновиков: {len(existing_drafts)} записей")

    if not traces:
        print("⚠️ Нет traces — нечему учиться.")
        return

    # 2. Извлекаем успешные паттерны
    patterns = extract_successful_patterns(traces)
    print(f"\n✅ Найдено {len(patterns)} успешных паттернов")

    # 3. Дедуплицируем
    new_drafts = deduplicate_drafts(patterns, existing_faq)
    print(f"🆕 Новых уникальных: {len(new_drafts)}")

    if not new_drafts:
        print("ℹ️ Нет новых паттернов для добавления.")
        return

    # 4. Сохраняем в черновики (НЕ в основной FAQ!)
    all_drafts = existing_drafts + new_drafts
    # Ограничиваем 100 черновиками
    all_drafts = all_drafts[-100:]
    save_json(FAQ_DRAFTS_PATH, all_drafts)
    
    print(f"\n💾 Сохранено {len(new_drafts)} новых черновиков → {FAQ_DRAFTS_PATH}")
    print(f"📋 Всего черновиков: {len(all_drafts)}")

    # 5. Logging
    learning_log = load_json(LEARNING_LOG_PATH, default=[])
    learning_log.append({
        "timestamp": datetime.now().isoformat(),
        "traces_analyzed": len(traces),
        "patterns_found": len(patterns),
        "new_drafts": len(new_drafts),
        "total_drafts": len(all_drafts),
        "total_faq": len(existing_faq)
    })
    save_json(LEARNING_LOG_PATH, learning_log[-50:])

    # 6. Показываем примеры
    print("\n📝 Примеры новых черновиков:")
    for d in new_drafts[:3]:
        print(f"  Q: {d['question'][:60]}")
        print(f"  A: {d['answer'][:100]}...")
        print()

    return new_drafts


def approve_drafts(indices=None):
    """Одобряет черновики и переносит в основной FAQ.
    indices: список индексов для одобрения. None = все.
    """
    drafts = load_json(FAQ_DRAFTS_PATH, default=[])
    faq = load_json(FAQ_CACHE_PATH)
    
    if not drafts:
        print("Нет черновиков для одобрения.")
        return
    
    if indices is None:
        to_approve = drafts
        remaining = []
    else:
        to_approve = [drafts[i] for i in indices if i < len(drafts)]
        remaining = [d for i, d in enumerate(drafts) if i not in indices]
    
    for draft in to_approve:
        faq[draft["question"]] = draft["answer"]
    
    save_json(FAQ_CACHE_PATH, faq)
    save_json(FAQ_DRAFTS_PATH, remaining)
    
    print(f"✅ Одобрено {len(to_approve)} записей → FAQ ({len(faq)} всего)")
    print(f"📝 Осталось черновиков: {len(remaining)}")


if __name__ == "__main__":
    run_learning()
