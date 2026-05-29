#!/usr/bin/env python3
"""
rag_lite.py — Легковесный RAG для VPS (без torch/transformers).

Использует BM25 (rank_bm25) для поиска по чанкам из PDF-библиотеки.
Чанки хранятся в JSON-файле (экспорт из ChromaDB).

Для VPS с 2GB RAM — идеальный вариант: ~20MB RAM, мгновенный поиск.

API:
    from rag_lite import search_knowledge, format_context_for_llm
    results = search_knowledge("температура инкубации Ross 308", top_k=5)
    context = format_context_for_llm(results)
"""

import json
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHUNKS_FILE = os.path.join(BASE_DIR, "..", "data", "rag_knowledge", "chunks.json")

# Маппинг английских PDF-имён → русские названия источников
_SOURCE_RU = {
    "03RSHowTo3MeasureEggShellTemperature-RU.pdf": "Как измерять температуру скорлупы яйца (Ross)",
    "AVIA-BestPractice-HatcheryTransfer-2015-RU.pdf": "Лучшие практики инкубатория — перенос яиц (Aviagen 2015)",
    "HatcheryTips-EN.pdf": "Советы по инкубации (Aviagen)",
    "Ross-Tech-Investigating-Hatchery-Practice_RUS.pdf": "Исследование практик инкубатория (Ross Tech)",
    "RossxRoss308_BroilerPerformanceObjectives2022_RU.pdf": "Целевые показатели бройлеров Ross 308 (2022)",
    "Russian Hatchery Guide 2020.pdf": "Руководство по инкубации (2020)",
    "ross.pdf": "Справочник Ross — выращивание бройлеров",
    "ross308-spravochnik.pdf": "Справочник по выращиванию бройлеров Ross 308",
    "rukovodstvo_kobb500.pdf": "Руководство по выращиванию Cobb 500",
    "Руководство по выращиванию РС Cobb 2021.pdf": "Руководство по выращиванию родительского стада Cobb (2021)",
    "Руководство по выращиванию бройлеров 2022.pdf": "Руководство по выращиванию бройлеров (2022)",
    "Руководство по процедуре вакцинации 2021 2.pdf": "Руководство по вакцинации (2021)",
    "Руководство по процедуре вакцинации 2021.pdf": "Руководство по вакцинации (2021)",
    "Руководство по рм и рс Orvia.pdf": "Руководство Orvia — ремонтный молодняк и родительское стадо",
    "черри вэлли руководство.pdf": "Руководство по выращиванию уток Черри Велли",
    "Приложение к руководству по выращиванию бройлеров 2022.pdf": "Приложение — выращивание бройлеров (2022)",
    "Приложение к руководству по содержанию родительских стад 2025 COBB-1.pdf": "Приложение — родительские стада Cobb (2025)",
    "Приложение к руководству по содержанию родительских стад 2025 COBB.pdf": "Приложение — родительские стада Cobb (2025)",
}


def _ru_source(filename: str) -> str:
    """Возвращает русское название источника."""
    return _SOURCE_RU.get(filename, filename.replace('.pdf', '').replace('_', ' '))


# Ленивая инициализация
_bm25 = None
_chunks = None


def _tokenize(text: str) -> list[str]:
    """Простая токенизация для русского/английского текста."""
    text = text.lower()
    # Убираем пунктуацию, оставляем буквы и цифры
    tokens = re.findall(r'[а-яёa-z0-9]+', text)
    # Убираем стоп-слова (минимальный набор)
    stop = {'и', 'в', 'на', 'с', 'по', 'для', 'из', 'от', 'к', 'за', 'не',
            'что', 'как', 'это', 'при', 'или', 'но', 'да', 'же', 'то', 'ли',
            'a', 'the', 'is', 'in', 'of', 'to', 'and', 'for', 'on', 'at'}
    return [t for t in tokens if t not in stop and len(t) > 1]


def _load():
    """Загружает чанки и строит BM25 индекс."""
    global _bm25, _chunks

    if _chunks is not None:
        return

    if not os.path.exists(CHUNKS_FILE):
        print(f"⚠️ RAG: файл чанков не найден: {CHUNKS_FILE}")
        _chunks = []
        return

    with open(CHUNKS_FILE, 'r', encoding='utf-8') as f:
        _chunks = json.load(f)

    if not _chunks:
        return

    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        print("⚠️ RAG: rank_bm25 не установлен (pip install rank-bm25)")
        return

    corpus = [_tokenize(c["text"]) for c in _chunks]
    _bm25 = BM25Okapi(corpus)
    print(f"✅ RAG Lite загружен: {len(_chunks)} чанков из {len(set(c.get('source','') for c in _chunks))} PDF")


def search_knowledge(query: str, top_k: int = 5) -> list[dict]:
    """Поиск в базе знаний по птицеводству (BM25).

    Args:
        query: Вопрос пользователя
        top_k: Количество результатов

    Returns:
        list[dict] с ключами: text, source, page, score
    """
    _load()

    if not _chunks or _bm25 is None:
        return []

    tokens = _tokenize(query)
    if not tokens:
        return []

    scores = _bm25.get_scores(tokens)

    # Берём top_k с наибольшим score
    indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]

    results = []
    for idx, score in indexed:
        if score > 0:
            chunk = _chunks[idx]
            results.append({
                "text": chunk["text"],
                "source": chunk.get("source", "?"),
                "page": chunk.get("page", 0),
                "score": round(float(score), 4),
            })

    return results


def format_context_for_llm(results: list[dict], max_chars: int = 2000) -> str:
    """Форматирует результаты RAG для промпта LLM.
    Стиль: уверенный, профессиональный, со ссылками на источники."""
    if not results:
        return ""

    lines = ["""📚 ЭКСПЕРТНЫЕ ДАННЫЕ ИЗ ПРОФЕССИОНАЛЬНЫХ РУКОВОДСТВ:
🔴 ПРАВИЛО: Используй эти данные КАК ОСНОВУ ответа. Отвечай УВЕРЕННО и ПРОФЕССИОНАЛЬНО.
НЕ пиши "не нашла в базе" или "из общих знаний". Пиши "Согласно руководству [название]...".
Обязательно указывай источник НА РУССКОМ ЯЗЫКЕ (название руководства и страницу).\n"""]
    total = 0

    for i, r in enumerate(results, 1):
        text = r["text"]
        if total + len(text) > max_chars:
            text = text[:max_chars - total]

        source_ru = _ru_source(r['source'])
        lines.append(f"[{i}] 📖 {source_ru}, стр. {r['page']}:")
        lines.append(f"  {text}")
        lines.append("")
        total += len(text) + 50

        if total >= max_chars:
            break

    return "\n".join(lines)


# Проверка при прямом запуске
if __name__ == "__main__":
    import sys
    _load()
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "температура инкубации бройлеров"
    print(f"\n🔍 Поиск: «{q}»\n")
    results = search_knowledge(q, top_k=5)
    if not results:
        print("❌ Ничего не найдено")
    else:
        for r in results:
            print(f"  [{r['score']}] {r['source']}, стр. {r['page']}")
            print(f"    {r['text'][:200]}\n")
        print("\n" + format_context_for_llm(results))
