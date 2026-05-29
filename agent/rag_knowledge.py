#!/usr/bin/env python3
"""
rag_knowledge.py — RAG-система знаний по птицеводству для IncuBird.

Индексирует PDF-библиотеку в ChromaDB с sentence-transformers эмбеддингами.
Используется агентами:
  - Анжела Заботкина (CRM-бот) — ответы клиентам на основе реальных знаний
  - Шекспир (контент) — статьи на основе экспертных данных, не выдумок

Архитектура:
  PDF → PyMuPDF → чанки (500 символов, overlap 100) → 
  → sentence-transformers (multilingual-e5-base) → ChromaDB (persistent)

Запуск:
  python3 rag_knowledge.py --index          # Индексация всех PDF
  python3 rag_knowledge.py --query "температура инкубации"  # Тест поиска
  python3 rag_knowledge.py --stats          # Статистика базы

API для агентов:
  from rag_knowledge import search_knowledge
  results = search_knowledge("какая температура инкубации для Ross 308?", top_k=5)

Утверждён: 06.05.2026 | v1
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime

# Пути
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG_DIR = os.path.join(BASE_DIR, "data", "rag_knowledge")
CHROMA_DIR = os.path.join(RAG_DIR, "chromadb")
PDF_SOURCE_DIR = "/Users/igorvasin/Documents/Литература-по-птицеводству"
COLLECTION_NAME = "incubird_knowledge"

# Модель эмбеддингов — multilingual, компактная (471MB), отлично работает с русским
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Параметры чанкинга
CHUNK_SIZE = 500       # символов
CHUNK_OVERLAP = 100    # перекрытие
MIN_CHUNK_SIZE = 50    # минимальный размер чанка


def _get_chroma_client():
    """Возвращает persistent ChromaDB клиент."""
    import chromadb
    os.makedirs(CHROMA_DIR, exist_ok=True)
    return chromadb.PersistentClient(path=CHROMA_DIR)


def _get_embedding_function():
    """Возвращает embedding function для ChromaDB."""
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    return SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL,
        # Для e5 моделей нужен префикс "query: " / "passage: "
    )


def _get_collection(client=None):
    """Возвращает или создаёт коллекцию."""
    if client is None:
        client = _get_chroma_client()
    ef = _get_embedding_function()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"description": "Библиотека знаний по птицеводству IncuBird"}
    )


# ════════════════════════════════════════════
# ИЗВЛЕЧЕНИЕ ТЕКСТА ИЗ PDF
# ════════════════════════════════════════════

def extract_text_from_pdf(pdf_path: str) -> list[dict]:
    """Извлекает текст из PDF постранично.
    
    Returns:
        list[dict] с ключами: page, text, source
    """
    import fitz  # pymupdf

    doc = fitz.open(pdf_path)
    pages = []
    filename = os.path.basename(pdf_path)
    
    for i, page in enumerate(doc):
        text = page.get_text()
        # Чистим мусор
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()
        if len(text) > MIN_CHUNK_SIZE:
            pages.append({
                "page": i + 1,
                "text": text,
                "source": filename,
            })
    
    doc.close()
    return pages


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Разбивает текст на чанки с перекрытием.
    
    Умный чанкинг: старается разбивать по параграфам/предложениям.
    """
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    # Разбиваем по параграфам
    paragraphs = re.split(r'\n\s*\n', text)
    
    current_chunk = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        # Если параграф сам по себе больше chunk_size — разбиваем по предложениям
        if len(para) > chunk_size:
            sentences = re.split(r'(?<=[.!?])\s+', para)
            for sent in sentences:
                if len(current_chunk) + len(sent) + 1 <= chunk_size:
                    current_chunk += (" " if current_chunk else "") + sent
                else:
                    if current_chunk and len(current_chunk) >= MIN_CHUNK_SIZE:
                        chunks.append(current_chunk)
                    # Overlap: берём хвост предыдущего чанка
                    if current_chunk and overlap > 0:
                        tail = current_chunk[-overlap:]
                        current_chunk = tail + " " + sent
                    else:
                        current_chunk = sent
        else:
            if len(current_chunk) + len(para) + 2 <= chunk_size:
                current_chunk += ("\n\n" if current_chunk else "") + para
            else:
                if current_chunk and len(current_chunk) >= MIN_CHUNK_SIZE:
                    chunks.append(current_chunk)
                # Overlap
                if current_chunk and overlap > 0:
                    tail = current_chunk[-overlap:]
                    current_chunk = tail + "\n\n" + para
                else:
                    current_chunk = para
    
    if current_chunk and len(current_chunk) >= MIN_CHUNK_SIZE:
        chunks.append(current_chunk)
    
    return chunks


# ════════════════════════════════════════════
# ИНДЕКСАЦИЯ
# ════════════════════════════════════════════

def index_pdf(pdf_path: str, collection=None) -> int:
    """Индексирует один PDF в ChromaDB.
    
    Returns:
        Количество проиндексированных чанков.
    """
    if collection is None:
        collection = _get_collection()
    
    filename = os.path.basename(pdf_path)
    print(f"  📄 {filename}...")
    
    # Извлекаем текст
    pages = extract_text_from_pdf(pdf_path)
    if not pages:
        print("     ⚠️ Нет текста")
        return 0
    
    # Чанкуем
    all_chunks = []
    for page_data in pages:
        chunks = chunk_text(page_data["text"])
        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(f"{filename}_{page_data['page']}_{i}_{chunk[:50]}".encode()).hexdigest()
            all_chunks.append({
                "id": chunk_id,
                "text": chunk,
                "metadata": {
                    "source": filename,
                    "page": page_data["page"],
                    "chunk_idx": i,
                    "char_count": len(chunk),
                }
            })
    
    if not all_chunks:
        return 0
    
    # Добавляем в ChromaDB батчами по 100
    for i in range(0, len(all_chunks), 100):
        batch = all_chunks[i:i+100]
        collection.upsert(
            ids=[c["id"] for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[c["metadata"] for c in batch],
        )
    
    print(f"     ✅ {len(all_chunks)} чанков ({sum(p['metadata']['char_count'] for p in all_chunks)} символов)")
    return len(all_chunks)


def index_all_pdfs(source_dir: str = PDF_SOURCE_DIR) -> dict:
    """Индексирует все PDF из директории.
    
    Returns:
        Статистика индексации.
    """
    print("\n📚 ИНДЕКСАЦИЯ БИБЛИОТЕКИ ПТИЦЕВОДСТВА")
    print(f"   Источник: {source_dir}")
    print(f"   Модель: {EMBEDDING_MODEL}")
    print(f"   Чанки: {CHUNK_SIZE} символов, overlap {CHUNK_OVERLAP}")
    print()
    
    client = _get_chroma_client()
    
    # Пересоздаём коллекцию для чистой индексации
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = _get_collection(client)
    
    pdf_files = sorted([
        f for f in os.listdir(source_dir)
        if f.lower().endswith('.pdf')
    ])
    
    if not pdf_files:
        print("❌ PDF файлов не найдено!")
        return {"status": "error", "message": "no PDFs found"}
    
    print(f"   📁 Найдено {len(pdf_files)} PDF:\n")
    
    stats = {"files": [], "total_chunks": 0, "total_chars": 0}
    
    for pdf_name in pdf_files:
        pdf_path = os.path.join(source_dir, pdf_name)
        try:
            n_chunks = index_pdf(pdf_path, collection)
            stats["files"].append({"name": pdf_name, "chunks": n_chunks})
            stats["total_chunks"] += n_chunks
        except Exception as e:
            print(f"  ❌ {pdf_name}: {e}")
            stats["files"].append({"name": pdf_name, "chunks": 0, "error": str(e)})
    
    stats["total_chars"] = collection.count()
    
    # Сохраняем метаданные
    meta_path = os.path.join(RAG_DIR, "index_meta.json")
    meta = {
        "indexed_at": datetime.now().isoformat(),
        "source_dir": source_dir,
        "model": EMBEDDING_MODEL,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "stats": stats,
    }
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'═' * 42}")
    print("✅ Индексация завершена!")
    print(f"   📊 Файлов: {len(pdf_files)}")
    print(f"   📦 Чанков: {stats['total_chunks']}")
    print(f"   💾 Хранилище: {CHROMA_DIR}")
    print(f"   📋 Метаданные: {meta_path}")
    
    return stats


# ════════════════════════════════════════════
# ПОИСК (API для агентов)
# ════════════════════════════════════════════

def search_knowledge(query: str, top_k: int = 5, source_filter: str = None) -> list[dict]:
    """Поиск в базе знаний по птицеводству.
    
    Основной API для Анжелы и Шекспира.
    
    Args:
        query: Вопрос пользователя
        top_k: Количество результатов (по умолчанию 5)
        source_filter: Фильтр по источнику (имя файла)
    
    Returns:
        list[dict] с ключами:
            text — текст чанка
            source — имя PDF-файла
            page — номер страницы
            distance — расстояние (чем меньше, тем релевантнее)
    """
    try:
        collection = _get_collection()
    except Exception as e:
        print(f"⚠️ RAG недоступен: {e}")
        return []
    
    if collection.count() == 0:
        return []
    
    # MiniLM не требует префикса (в отличие от e5 моделей)
    prefixed_query = query
    
    where_filter = None
    if source_filter:
        where_filter = {"source": source_filter}
    
    try:
        results = collection.query(
            query_texts=[prefixed_query],
            n_results=min(top_k, collection.count()),
            where=where_filter,
        )
    except Exception as e:
        print(f"⚠️ Ошибка поиска: {e}")
        return []
    
    # Форматируем результаты
    output = []
    if results and results.get("documents") and results["documents"][0]:
        docs = results["documents"][0]
        metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
        dists = results["distances"][0] if results.get("distances") else [0] * len(docs)
        
        for doc, meta, dist in zip(docs, metas, dists):
            output.append({
                "text": doc,
                "source": meta.get("source", "?"),
                "page": meta.get("page", 0),
                "distance": round(dist, 4),
            })
    
    return output


def format_context_for_llm(results: list[dict], max_chars: int = 3000) -> str:
    """Форматирует результаты RAG для промпта LLM.
    
    Используется при вставке в system prompt Анжелы/Шекспира.
    """
    if not results:
        return ""
    
    lines = ["📚 БАЗА ЗНАНИЙ ПО ПТИЦЕВОДСТВУ (экспертные источники):\n"]
    total = 0
    
    for i, r in enumerate(results, 1):
        text = r["text"]
        if total + len(text) > max_chars:
            text = text[:max_chars - total]
        
        lines.append(f"[{i}] Источник: {r['source']}, стр. {r['page']}")
        lines.append(f"    {text}")
        lines.append("")
        total += len(text) + 50
        
        if total >= max_chars:
            break
    
    lines.append("⚠️ Используй ТОЛЬКО эти данные для ответа. Не додумывай.")
    return "\n".join(lines)


# ════════════════════════════════════════════
# СТАТИСТИКА
# ════════════════════════════════════════════

def print_stats():
    """Печатает статистику базы знаний."""
    meta_path = os.path.join(RAG_DIR, "index_meta.json")
    if os.path.exists(meta_path):
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        print("\n📚 БАЗА ЗНАНИЙ INCUBIRD")
        print(f"   Проиндексировано: {meta['indexed_at']}")
        print(f"   Модель: {meta['model']}")
        print(f"   Чанки: {meta['chunk_size']} символов")
        print()
        for file_info in meta.get("stats", {}).get("files", []):
            status = "✅" if file_info.get("chunks", 0) > 0 else "❌"
            print(f"   {status} {file_info['name']}: {file_info.get('chunks', 0)} чанков")
        print(f"\n   📦 Всего чанков: {meta.get('stats', {}).get('total_chunks', '?')}")
    else:
        print("❌ База знаний не проиндексирована. Запусти: python3 rag_knowledge.py --index")
    
    try:
        collection = _get_collection()
        print(f"   🗄️ В ChromaDB: {collection.count()} документов")
    except Exception as e:
        print(f"   ⚠️ ChromaDB: {e}")


# ════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════

def main():
    args = sys.argv[1:]
    
    if "--index" in args:
        # Индексация
        source = PDF_SOURCE_DIR
        if "--source" in args:
            idx = args.index("--source")
            if idx + 1 < len(args):
                source = args[idx + 1]
        index_all_pdfs(source)
    
    elif "--query" in args:
        # Тестовый поиск
        idx = args.index("--query")
        if idx + 1 < len(args):
            query = args[idx + 1]
        else:
            query = "температура инкубации яиц бройлера"
        
        print(f"\n🔍 Поиск: «{query}»\n")
        results = search_knowledge(query, top_k=5)
        
        if not results:
            print("❌ Ничего не найдено")
            return
        
        for i, r in enumerate(results, 1):
            print(f"{'─' * 42}")
            print(f"[{i}] 📄 {r['source']}, стр. {r['page']} (dist: {r['distance']})")
            print(f"    {r['text'][:300]}")
            print()
        
        # Покажем форматированный контекст для LLM
        print(f"{'═' * 42}")
        print("📋 КОНТЕКСТ ДЛЯ LLM:")
        print(format_context_for_llm(results))
    
    elif "--stats" in args:
        print_stats()
    
    else:
        print("Использование:")
        print("  python3 rag_knowledge.py --index          # Индексация PDF")
        print("  python3 rag_knowledge.py --query 'текст'  # Тестовый поиск")
        print("  python3 rag_knowledge.py --stats           # Статистика")


if __name__ == "__main__":
    main()
