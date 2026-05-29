#!/usr/bin/env python3
"""
vector_memory.py — Векторный поиск по памяти (Phase 2).

Стек (Hybrid RAG Lite — без фреймворков):
- Gemini Embedding 2 (3072 dim) через REST API + SOCKS5 прокси
- FAISS (локальный, 0 зависимостей)
- TF-IDF (sklearn) — keyword backup
- RRF (Reciprocal Rank Fusion) — объединение результатов

Примечание: gRPC SDK (google-generativeai) заблокирован по региону.
Используем REST API через SOCKS5 прокси (тот же что для Telegram).

Связан с:
- kulibin-engineer/SKILL.md → Gemini Embedding 2 (ADOPT), Hybrid RAG Lite (ADOPT)
- knowledge/agent-memory-architecture/ (SQLite решение)
- agent/memory_graph.py (Phase 1 — граф связей)
"""

import os
import pickle
import time

import numpy as np
import requests

# Lazy imports
faiss = None
TfidfVectorizer = None
cosine_similarity = None

EMBED_MODEL = "gemini-embedding-2-preview"  # Gemini Embedding 2 (3072 dim)
EMBED_DIM = 3072
GEMINI_REST_URL = "https://generativelanguage.googleapis.com/v1beta/models"
INDEX_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "vector_index")


def _init_deps():
    """Ленивая загрузка зависимостей."""
    global faiss, TfidfVectorizer, cosine_similarity
    if faiss is None:
        import faiss as _faiss
        faiss = _faiss
    if TfidfVectorizer is None:
        from sklearn.feature_extraction.text import TfidfVectorizer as _Tfidf
        from sklearn.metrics.pairwise import cosine_similarity as _cs
        TfidfVectorizer = _Tfidf
        cosine_similarity = _cs


def _get_proxies():
    """SOCKS5 прокси из .env (тот же что для Telegram)."""
    proxy = os.getenv("TELEGRAM_PROXY", "")
    if proxy:
        return {"https": proxy, "http": proxy}
    return None


class VectorMemory:
    """Векторный поиск по текстовым фактам.

    Два канала поиска (Hybrid RAG Lite):
    1. Семантический — Gemini Embedding 2 + FAISS (cosine)
    2. Ключевой — TF-IDF (sklearn)
    Результаты объединяются через RRF.
    """

    def __init__(self, index_dir: str = INDEX_DIR):
        _init_deps()
        self.index_dir = index_dir
        os.makedirs(index_dir, exist_ok=True)

        self.index_path = os.path.join(index_dir, "faiss.index")
        self.meta_path = os.path.join(index_dir, "metadata.pkl")
        self.tfidf_path = os.path.join(index_dir, "tfidf.pkl")

        # FAISS index (Inner Product — cosine после нормализации)
        self.index = None
        self.metadata = []  # [{node_id, chat_id, text, ...}]
        self.tfidf = None
        self.tfidf_matrix = None

        self._load()

    def _load(self):
        """Загрузка индексов с диска."""
        if os.path.exists(self.index_path):
            self.index = faiss.read_index(self.index_path)
        else:
            self.index = faiss.IndexFlatIP(EMBED_DIM)  # Inner Product

        if os.path.exists(self.meta_path):
            with open(self.meta_path, "rb") as f:
                self.metadata = pickle.load(f)

        if os.path.exists(self.tfidf_path):
            with open(self.tfidf_path, "rb") as f:
                saved = pickle.load(f)
                self.tfidf = saved["vectorizer"]
                self.tfidf_matrix = saved["matrix"]

    def _save(self):
        """Сохранение индексов на диск."""
        faiss.write_index(self.index, self.index_path)
        with open(self.meta_path, "wb") as f:
            pickle.dump(self.metadata, f)
        if self.tfidf is not None:
            with open(self.tfidf_path, "wb") as f:
                pickle.dump({"vectorizer": self.tfidf, "matrix": self.tfidf_matrix}, f)

    # ─── Эмбеддинг ─────────────────────────────────────────────────

    def embed_text(self, text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> np.ndarray:
        """Получает эмбеддинг через Gemini REST API + SOCKS5 прокси.

        task_type:
            RETRIEVAL_DOCUMENT — при индексации
            RETRIEVAL_QUERY — при поиске
        """
        api_key = os.getenv("GEMINI_API_KEY")
        url = f"{GEMINI_REST_URL}/{EMBED_MODEL}:embedContent?key={api_key}"
        payload = {
            "model": f"models/{EMBED_MODEL}",
            "content": {"parts": [{"text": text}]},
            "taskType": task_type
        }
        resp = requests.post(url, json=payload, proxies=_get_proxies(), timeout=120)
        resp.raise_for_status()
        vec = np.array(resp.json()["embedding"]["values"], dtype=np.float32)
        # Нормализация для cosine similarity через Inner Product
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def embed_batch(self, texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> np.ndarray:
        """Батч-эмбеддинг через REST API. Фоллбэк на поштучный если batch не доступен."""
        api_key = os.getenv("GEMINI_API_KEY")

        vectors = []
        for i, text in enumerate(texts):
            vec = self.embed_text(text, task_type=task_type)
            vectors.append(vec)
            if (i + 1) % 10 == 0:
                print(f"    ... {i+1}/{len(texts)} эмбеддингов")
            time.sleep(0.1)  # rate limit

        return np.array(vectors, dtype=np.float32)

    # ─── Индексация ─────────────────────────────────────────────────

    def add_texts(self, items: list[dict]):
        """Добавляет тексты в оба индекса.

        items: [{"node_id": "...", "chat_id": "...", "text": "...", ...}]
        """
        if not items:
            return

        texts = [item["text"] for item in items]

        # 1. Векторный индекс (FAISS)
        vectors = self.embed_batch(texts)
        self.index.add(vectors)
        self.metadata.extend(items)

        # 2. TF-IDF индекс (rebuild)
        all_texts = [m["text"] for m in self.metadata]
        self.tfidf = TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 2),
            # Русский + английский
            token_pattern=r"(?u)\b\w[\w-]+\b"
        )
        self.tfidf_matrix = self.tfidf.fit_transform(all_texts)

        self._save()
        print(f"  ✅ Добавлено {len(items)} текстов. Всего: {self.index.ntotal}")

    # ─── Поиск ──────────────────────────────────────────────────────

    def search_vector(self, query: str, top_k: int = 10) -> list[dict]:
        """Семантический поиск через FAISS."""
        if self.index.ntotal == 0:
            return []

        q_vec = self.embed_text(query, task_type="RETRIEVAL_QUERY")
        q_vec = q_vec.reshape(1, -1)

        scores, indices = self.index.search(q_vec, min(top_k, self.index.ntotal))
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0 and idx < len(self.metadata):
                item = self.metadata[idx].copy()
                item["score_vector"] = float(score)
                results.append(item)
        return results

    def search_keyword(self, query: str, top_k: int = 10) -> list[dict]:
        """Ключевой поиск через TF-IDF."""
        if self.tfidf is None or self.tfidf_matrix is None:
            return []

        q_vec = self.tfidf.transform([query])
        scores = cosine_similarity(q_vec, self.tfidf_matrix).flatten()
        top_indices = scores.argsort()[::-1][:top_k]

        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                item = self.metadata[idx].copy()
                item["score_tfidf"] = float(scores[idx])
                results.append(item)
        return results

    def hybrid_search(self, query: str, top_k: int = 5, k: int = 60) -> list[dict]:
        """Hybrid Search: Vector + TF-IDF → RRF ранжирование.

        RRF (Reciprocal Rank Fusion):
        score(d) = Σ 1/(k + rank_i(d))
        где k=60 (стандарт), rank_i — позиция в i-м списке.
        """
        vec_results = self.search_vector(query, top_k=top_k * 3)
        kw_results = self.search_keyword(query, top_k=top_k * 3)

        # RRF
        rrf_scores = {}
        for rank, item in enumerate(vec_results):
            nid = item["node_id"]
            rrf_scores[nid] = rrf_scores.get(nid, 0) + 1.0 / (k + rank + 1)
            if nid not in rrf_scores:
                rrf_scores[nid] = {"item": item, "score": 0}

        items_map = {}
        for item in vec_results + kw_results:
            items_map[item["node_id"]] = item

        rrf_scores = {}
        for rank, item in enumerate(vec_results):
            nid = item["node_id"]
            rrf_scores[nid] = rrf_scores.get(nid, 0) + 1.0 / (k + rank + 1)
        for rank, item in enumerate(kw_results):
            nid = item["node_id"]
            rrf_scores[nid] = rrf_scores.get(nid, 0) + 1.0 / (k + rank + 1)

        # Сортировка по RRF score
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

        results = []
        for nid in sorted_ids[:top_k]:
            item = items_map[nid].copy()
            item["score_rrf"] = rrf_scores[nid]
            results.append(item)
        return results

    # ─── Статистика ─────────────────────────────────────────────────

    def stats(self) -> dict:
        return {
            "total_vectors": self.index.ntotal,
            "dimension": EMBED_DIM,
            "model": EMBED_MODEL,
            "has_tfidf": self.tfidf is not None
        }


# ─── Demo ───────────────────────────────────────────────────────────

def demo():
    """Демо: индексируем товары VezemCip и ищем."""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

    vm = VectorMemory()

    # Товары из unified_brain.json
    products = [
        {"node_id": "prod_kobb500", "chat_id": "catalog",
         "text": "Бройлерные цыплята Кобб-500. Цена 90 рублей за штуку. Вакцинация: ИБК, Ньюкасла, Гамборо. Документация: ветсвидетельство через Меркурий. Доставка по Крыму, Ростовской области, Краснодарскому краю."},
        {"node_id": "prod_ross308", "chat_id": "catalog",
         "text": "Бройлерные цыплята Росс-308. Цена 85 рублей за штуку. Быстрый рост, хорошая конверсия корма. Вакцинация по схеме. Подходит для начинающих фермеров."},
        {"node_id": "prod_st5", "chat_id": "catalog",
         "text": "Бройлерные цыплята СТ-5. Цена 85 рублей. Коричневые бройлеры. Уникальная порода, не требует специальных условий содержания."},
        {"node_id": "prod_arbor", "chat_id": "catalog",
         "text": "Бройлеры породы Арбор Айкрес. Цена 53 рубля. Бюджетный вариант. Подходит для массового выращивания."},
        {"node_id": "prod_podrost", "chat_id": "catalog",
         "text": "Подрост цыплят Кобб-500, возраст 7-14 дней. Цена 70-80 рублей. Уже вакцинированы и адаптированы. Меньше потерь при выращивании."},
        {"node_id": "delivery_crimea", "chat_id": "logistics",
         "text": "Доставка бройлеров по Крыму. Точки выдачи: Симферополь (Киевская 144), Джанкой, Армянск, Севастополь. Машина приезжает по вторникам и четвергам."},
        {"node_id": "delivery_rostov", "chat_id": "logistics",
         "text": "Доставка бройлеров по Ростовской области. Точки: Таганрог (Азовская 3), Ростов-на-Дону, Батайск, Азов. Еженедельные рейсы."},
        {"node_id": "delivery_kuban", "chat_id": "logistics",
         "text": "Доставка бройлеров по Краснодарскому краю. Армавир (Ленина 76), Темрюк (Ленина 1), Краснодар, Новороссийск."},
        {"node_id": "vacc_info", "chat_id": "veterinary",
         "text": "Схема вакцинации бройлеров: 1-й день — ИБК (инфекционный бронхит кур), 7-й день — болезнь Ньюкасла, 14-й день — болезнь Гамборо. Все прививки сертифицированы, документы предоставляются."},
    ]

    print(f"📦 Индексируем {len(products)} записей...")
    vm.add_texts(products)
    print()

    # Тестовые запросы
    queries = [
        "Какие цыплята подешевле?",
        "Когда машина в Крым?",
        "Какие прививки делают бройлерам?",
        "Доставка в Таганрог",
    ]

    for q in queries:
        print(f"🔍 «{q}»")
        results = vm.hybrid_search(q, top_k=3)
        for i, r in enumerate(results, 1):
            print(f"   {i}. [{r['node_id']}] RRF={r['score_rrf']:.4f}")
            print(f"      {r['text'][:80]}...")
        print()


if __name__ == "__main__":
    demo()
