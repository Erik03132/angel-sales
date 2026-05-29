"""
🧩 Tool-Result Digest — сжатие контекста перед подачей в LLM
═══════════════════════════════════════════════════════════════
Вдохновлено: Jarvis (isair/jarvis) — Tool-result Digest pattern.

Проблема: RAG/BM25/Vector возвращают сырые куски текста (2000+ символов),
которые забивают контекстное окно LLM и снижают качество ответов.

Решение: Лёгкий digest-слой, который:
1. Дедуплицирует повторяющиеся фрагменты
2. Извлекает ключевые факты (цены, даты, имена)
3. Сжимает до компактного "attributed fact note"
4. Опционально — LLM-дистилляция для сложных текстов

Результат: 2000+ символов → 300-500 символов (+атрибуция источника)
"""

import os
import re
import time
from typing import Optional

# === КОНФИГУРАЦИЯ ===

# Максимальная длина дайджеста (символы)
MAX_DIGEST_CHARS = int(os.getenv("DIGEST_MAX_CHARS", "500"))

# Включить LLM-дистилляцию (медленно, но точнее)
LLM_DIGEST_ENABLED = os.getenv("LLM_DIGEST_ENABLED", "false").lower() == "true"

# Таймаут LLM-дистилляции (секунды)
LLM_DIGEST_TIMEOUT = int(os.getenv("LLM_DIGEST_TIMEOUT", "8"))

# Минимальный размер контекста для активации дайджеста
MIN_CONTEXT_FOR_DIGEST = int(os.getenv("DIGEST_MIN_CHARS", "800"))


# === ПАТТЕРНЫ ИЗВЛЕЧЕНИЯ ФАКТОВ ===

# Цены (основной бизнес — птица)
PRICE_PATTERN = re.compile(
    r'(\d+)\s*₽|(\d+)\s*руб|цена\s*[:\-–—]?\s*(\d+)|стоимость\s*[:\-–—]?\s*(\d+)|от\s+(\d+)\s*₽',
    re.IGNORECASE
)

# Породы птиц (для атрибуции)
BREED_PATTERN = re.compile(
    r'(?:КОББ|РОСС|Доминант|Ломан|Хайсекс|Мулард|Агидель|Биг-6|Линда|'
    r'Мастер Грей|Ред Бро|Голошейка|Farm Color|Гриз Бар|Бронза|Хайбрид|'
    r'Грейд Мейкер|Голубой фаворит|Черри Велли|Цесарк|Адлерская)',
    re.IGNORECASE
)

# Даты и сроки
DATE_PATTERN = re.compile(
    r'\d{1,2}\.\d{1,2}\.\d{2,4}|\d{1,2}\s+(?:янв|фев|мар|апр|мая|июн|июл|авг|сен|окт|ноя|дек)',
    re.IGNORECASE
)

# Телефоны
PHONE_PATTERN = re.compile(r'(?:\+7|8)\s*[\(\-]?\d{3}[\)\-]?\s*\d{3}[\-\s]?\d{2}[\-\s]?\d{2}')


def digest_context(raw_context: str, query: str = "", source_label: str = "RAG") -> str:
    """
    Сжимает сырой контекст в компактный дайджест.
    
    Args:
        raw_context: Сырой текст из RAG/BM25/Vector поиска
        query: Исходный вопрос пользователя (для релевантности)
        source_label: Метка источника (RAG, BM25, Vector, Каталог)
    
    Returns:
        Сжатый контекст с атрибуцией
    """
    if not raw_context or len(raw_context) < MIN_CONTEXT_FOR_DIGEST:
        return raw_context  # Слишком маленький — не трогаем
    
    start_time = time.time()
    original_len = len(raw_context)
    
    # Шаг 1: Разбиваем на фрагменты
    fragments = _split_fragments(raw_context)
    
    # Шаг 2: Дедупликация
    unique_fragments = _dedup_fragments(fragments)
    
    # Шаг 3: Ранжирование по релевантности к запросу
    if query:
        ranked = _rank_by_relevance(unique_fragments, query)
    else:
        ranked = unique_fragments
    
    # Шаг 4: Извлечение ключевых фактов
    key_facts = _extract_key_facts(raw_context)
    
    # Шаг 5: Сборка дайджеста
    digest = _assemble_digest(ranked, key_facts, source_label)
    
    # Шаг 6: Обрезка до лимита
    if len(digest) > MAX_DIGEST_CHARS:
        digest = _smart_truncate(digest, MAX_DIGEST_CHARS)
    
    elapsed = time.time() - start_time
    ratio = len(digest) / original_len if original_len > 0 else 0
    print(f"🧩 Digest ({source_label}): {original_len} → {len(digest)} символов "
          f"({ratio:.0%}) за {elapsed:.2f}с")
    
    return digest


def digest_product_context(raw_catalog: str, query: str = "") -> str:
    """Специализированный дайджест для каталога товаров."""
    if not raw_catalog or len(raw_catalog) < 200:
        return raw_catalog
    
    lines = raw_catalog.strip().split('\n')
    header = lines[0] if lines else ""
    
    # Извлекаем товарные строки
    items = [l.strip() for l in lines[1:] if l.strip()]
    
    if not items:
        return raw_catalog
    
    # Если есть запрос — фильтруем по релевантности
    if query:
        query_words = set(re.findall(r'\w{3,}', query.lower()))
        scored_items = []
        for item in items:
            item_words = set(re.findall(r'\w{3,}', item.lower()))
            overlap = len(query_words & item_words)
            scored_items.append((overlap, item))
        scored_items.sort(key=lambda x: -x[0])
        # Берём топ-5 самых релевантных
        items = [item for _, item in scored_items[:5]]
    else:
        items = items[:5]  # Без запроса — первые 5
    
    result = header + '\n' + '\n'.join(items)
    print(f"🧩 Catalog digest: {len(raw_catalog)} → {len(result)} символов, {len(items)} товаров")
    return result


def digest_vector_context(raw_vector: str, query: str = "") -> str:
    """Специализированный дайджест для векторного/RAG контекста."""
    if not raw_vector or len(raw_vector) < MIN_CONTEXT_FOR_DIGEST:
        return raw_vector
    
    # Разбиваем по источникам (BM25:, Vector:, Hybrid:, 📖)
    sources = re.split(r'(?=(?:BM25:|Vector:|Hybrid\[|📖))', raw_vector)
    sources = [s.strip() for s in sources if s.strip()]
    
    if not sources:
        return raw_vector
    
    # Дедупликация по содержимому (часто BM25 и Vector находят то же самое)
    seen_content = set()
    unique_sources = []
    for src in sources:
        # Нормализуем для сравнения (убираем метки, берём первые 100 символов)
        normalized = re.sub(r'^(BM25|Vector|Hybrid\[\w+\]):\s*', '', src)[:100].lower()
        content_hash = hash(normalized)
        if content_hash not in seen_content:
            seen_content.add(content_hash)
            unique_sources.append(src)
    
    deduped = len(sources) - len(unique_sources)
    if deduped > 0:
        print(f"🧹 Vector dedup: убрано {deduped} дубликатов")
    
    # Ранжируем по релевантности
    if query:
        query_words = set(re.findall(r'\w{3,}', query.lower()))
        scored = []
        for src in unique_sources:
            src_words = set(re.findall(r'\w{3,}', src.lower()))
            overlap = len(query_words & src_words)
            # Бонус за наличие цен
            if PRICE_PATTERN.search(src):
                overlap += 2
            # Бонус за наличие пород
            if BREED_PATTERN.search(src):
                overlap += 1
            scored.append((overlap, src))
        scored.sort(key=lambda x: -x[0])
        unique_sources = [src for _, src in scored]
    
    # Берём топ-3 самых релевантных + обрезаем каждый до 200 символов
    trimmed = []
    for src in unique_sources[:3]:
        if len(src) > 250:
            # Обрезаем, но сохраняем полные предложения
            truncated = _smart_truncate(src, 250)
            trimmed.append(truncated)
        else:
            trimmed.append(src)
    
    result = '\n'.join(trimmed)
    
    original_len = len(raw_vector)
    print(f"🧩 Vector digest: {original_len} → {len(result)} символов, "
          f"{len(unique_sources)} уникальных из {len(sources)}")
    
    return result


# === ВНУТРЕННИЕ ФУНКЦИИ ===

def _split_fragments(text: str) -> list:
    """Разбивает текст на смысловые фрагменты."""
    # Разделители: пустые строки, маркеры источников, нумерованные списки
    fragments = re.split(r'\n\s*\n|\n(?=\d+\.)|(?=BM25:|Vector:|Hybrid\[|📖)', text)
    return [f.strip() for f in fragments if f.strip() and len(f.strip()) > 10]


def _dedup_fragments(fragments: list) -> list:
    """Убирает дубликаты (одинаковый контент из разных источников)."""
    seen = set()
    unique = []
    for frag in fragments:
        # Нормализуем: убираем метки, lowercase, первые 80 символов
        norm = re.sub(r'^(BM25|Vector|Hybrid\[\w+\]|📖\s*\w+):\s*', '', frag)
        norm_key = norm[:80].lower().strip()
        if norm_key not in seen:
            seen.add(norm_key)
            unique.append(frag)
    return unique


def _rank_by_relevance(fragments: list, query: str) -> list:
    """Ранжирует фрагменты по релевантности к запросу."""
    query_words = set(re.findall(r'\w{3,}', query.lower()))
    if not query_words:
        return fragments
    
    scored = []
    for frag in fragments:
        frag_words = set(re.findall(r'\w{3,}', frag.lower()))
        overlap = len(query_words & frag_words)
        
        # Бонусы за ключевую информацию
        if PRICE_PATTERN.search(frag):
            overlap += 3  # Цены — высокий приоритет
        if BREED_PATTERN.search(frag):
            overlap += 2  # Породы
        if DATE_PATTERN.search(frag):
            overlap += 1  # Даты
        
        scored.append((overlap, frag))
    
    scored.sort(key=lambda x: -x[0])
    return [frag for _, frag in scored]


def _extract_key_facts(text: str) -> list:
    """Извлекает ключевые факты из текста."""
    facts = []
    
    # Цены
    prices = PRICE_PATTERN.findall(text)
    if prices:
        # Находим контекст вокруг цен
        for match in PRICE_PATTERN.finditer(text):
            start = max(0, match.start() - 30)
            end = min(len(text), match.end() + 10)
            context = text[start:end].strip()
            # Чистим
            context = re.sub(r'\s+', ' ', context)
            if context and context not in facts:
                facts.append(f"💰 {context}")
    
    # Телефоны
    phones = PHONE_PATTERN.findall(text)
    for phone in phones[:2]:
        facts.append(f"📞 {phone}")
    
    return facts[:5]  # Макс 5 ключевых фактов


def _assemble_digest(ranked_fragments: list, key_facts: list, source_label: str) -> str:
    """Собирает финальный дайджест."""
    parts = []
    
    # Топ-3 самых релевантных фрагмента (обрезанные)
    for frag in ranked_fragments[:3]:
        if len(frag) > 200:
            frag = _smart_truncate(frag, 200)
        parts.append(frag)
    
    # Ключевые факты (если не дублируют фрагменты)
    existing_text = ' '.join(parts).lower()
    for fact in key_facts:
        fact_core = re.sub(r'^[💰📞]\s*', '', fact).lower()
        if fact_core[:20] not in existing_text:
            parts.append(fact)
    
    return '\n'.join(parts)


def _smart_truncate(text: str, max_chars: int) -> str:
    """Обрезает текст по границе предложения."""
    if len(text) <= max_chars:
        return text
    
    # Ищем последнюю точку/восклицательный/вопросительный знак до лимита
    truncated = text[:max_chars]
    
    # Ищем последний разделитель предложения
    last_period = max(
        truncated.rfind('.'),
        truncated.rfind('!'),
        truncated.rfind('?'),
        truncated.rfind('\n'),
    )
    
    if last_period > max_chars * 0.5:  # Если нашли разделитель в последней половине
        return truncated[:last_period + 1]
    
    # Иначе обрезаем по последнему пробелу
    last_space = truncated.rfind(' ')
    if last_space > max_chars * 0.7:
        return truncated[:last_space] + '…'
    
    return truncated + '…'


# === LLM-ДИСТИЛЛЯЦИЯ (опционально) ===

def llm_digest(raw_context: str, query: str, call_llm_fn=None) -> Optional[str]:
    """
    LLM-дистилляция: сжимает сырой контекст через маленькую модель.
    Использует отдельный быстрый вызов LLM для создания краткого саммари.
    
    Args:
        raw_context: Сырой контекст для сжатия
        query: Вопрос пользователя  
        call_llm_fn: Функция вызова LLM (из angelochka_core)
    
    Returns:
        Сжатый контекст или None если не удалось
    """
    if not LLM_DIGEST_ENABLED or not call_llm_fn:
        return None
    
    if len(raw_context) < 1000:
        return None  # Слишком мало для дистилляции
    
    digest_prompt = f"""Сожми следующий контекст в 2-3 предложения, сохранив ТОЛЬКО факты, 
релевантные вопросу. Обязательно сохрани: цены, породы, даты, телефоны.

ВОПРОС: {query}

КОНТЕКСТ ДЛЯ СЖАТИЯ:
{raw_context[:2000]}

СЖАТЫЙ ОТВЕТ (макс 300 символов):"""
    
    try:
        import requests
        # Используем самую дешёвую/быструю модель
        openrouter_key = os.getenv("OPENROUTER_KEY", "")
        if not openrouter_key:
            return None
        
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {openrouter_key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek/deepseek-chat-v3-0324:free",
                "messages": [{"role": "user", "content": digest_prompt}],
                "max_tokens": 200,
            },
            timeout=LLM_DIGEST_TIMEOUT,
            proxies={"http": None, "https": None}
        )
        data = resp.json()
        if "choices" in data:
            digest = data["choices"][0]["message"]["content"].strip()
            print(f"🧩 LLM digest: {len(raw_context)} → {len(digest)} символов")
            return digest
    except Exception as e:
        print(f"⚠️ LLM digest failed: {e}")
    
    return None
