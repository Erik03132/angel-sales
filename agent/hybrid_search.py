"""
Гибридный поиск: BM25 (лексический) + Vector (семантический).
BM25 отлично ищет точные названия: «Д-107», «Биг-6», «Кобб-500».
Vector ищет по смыслу: «хочу птицу на мясо побольше» → индюки.
Результаты объединяются по формуле RRF (Reciprocal Rank Fusion).
"""
import os
import re
import json
import math
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')


class BM25:
    """BM25 лексический поиск по каталогу товаров."""
    
    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.documents = []      # [{id, content, metadata}]
        self.doc_lengths = []
        self.avg_dl = 0
        self.term_freq = []       # [{term: count}] для каждого документа
        self.doc_freq = defaultdict(int)  # term → в скольких документах встречается
        self.N = 0
    
    def _tokenize(self, text):
        """Простая токенизация: lowercase, удаление пунктуации."""
        text = text.lower()
        text = re.sub(r'[^\w\s\-]', ' ', text)
        return [w for w in text.split() if len(w) > 1]
    
    def index(self, documents):
        """Индексирует список документов [{id, content, metadata}]."""
        self.documents = documents
        self.N = len(documents)
        self.term_freq = []
        self.doc_freq = defaultdict(int)
        self.doc_lengths = []
        
        for doc in documents:
            tokens = self._tokenize(doc.get("content", ""))
            self.doc_lengths.append(len(tokens))
            
            tf = defaultdict(int)
            seen = set()
            for token in tokens:
                tf[token] += 1
                if token not in seen:
                    self.doc_freq[token] += 1
                    seen.add(token)
            
            self.term_freq.append(dict(tf))
        
        self.avg_dl = sum(self.doc_lengths) / max(self.N, 1)
    
    def search(self, query, limit=5):
        """Поиск по BM25 score."""
        query_tokens = self._tokenize(query)
        scores = []
        
        for i in range(self.N):
            score = 0
            dl = self.doc_lengths[i]
            
            for term in query_tokens:
                if term not in self.term_freq[i]:
                    continue
                
                tf = self.term_freq[i][term]
                df = self.doc_freq.get(term, 0)
                
                # IDF
                idf = math.log((self.N - df + 0.5) / (df + 0.5) + 1)
                
                # TF component
                tf_norm = (tf * (self.k1 + 1)) / (tf + self.k1 * (1 - self.b + self.b * dl / self.avg_dl))
                
                score += idf * tf_norm
            
            if score > 0:
                scores.append((i, score))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        
        results = []
        for idx, score in scores[:limit]:
            doc = self.documents[idx].copy()
            doc["bm25_score"] = score
            results.append(doc)
        
        return results


def hybrid_search(query, vector_results=None, bm25_index=None, limit=5, alpha=0.5):
    """
    Объединяет результаты BM25 и Vector Search через RRF.
    alpha: вес векторного поиска (0.5 = равный, 0.7 = больше вектора).
    """
    k = 60  # RRF constant
    
    rrf_scores = defaultdict(float)
    doc_map = {}
    
    # BM25 результаты
    if bm25_index:
        bm25_results = bm25_index.search(query, limit=limit * 2)
        for rank, doc in enumerate(bm25_results):
            doc_id = doc.get("id", str(rank))
            rrf_scores[doc_id] += (1 - alpha) * (1 / (k + rank + 1))
            doc_map[doc_id] = doc
    
    # Vector результаты
    if vector_results:
        for rank, doc in enumerate(vector_results):
            doc_id = doc.get("id", doc.get("content", "")[:50])
            rrf_scores[doc_id] += alpha * (1 / (k + rank + 1))
            if doc_id not in doc_map:
                doc_map[doc_id] = doc
    
    # Сортируем по RRF score
    sorted_ids = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    
    results = []
    for doc_id, score in sorted_ids[:limit]:
        doc = doc_map.get(doc_id, {})
        doc["hybrid_score"] = score
        results.append(doc)
    
    return results


# Глобальный BM25 индекс — инициализируется при импорте
_bm25 = BM25()
_brain_path = os.path.join(DATA_DIR, 'angelochka_unified_brain.json')

def init_bm25_index():
    """Загружает данные из brain и строит BM25 индекс."""
    global _bm25
    if os.path.exists(_brain_path):
        with open(_brain_path, 'r', encoding='utf-8') as f:
            brain = json.load(f)
        _bm25.index(brain)
        print(f"✅ BM25 индекс: {len(brain)} документов")
    return _bm25

def bm25_search(query, limit=5):
    """Быстрый BM25 поиск по каталогу."""
    return _bm25.search(query, limit=limit)

# Автоинициализация
init_bm25_index()


if __name__ == "__main__":
    tests = [
        "Д-107",
        "Биг-6",
        "Кобб-500",
        "хочу утку",
        "какой корм для бройлеров",
    ]
    for q in tests:
        results = bm25_search(q, limit=3)
        print(f"\n🔍 '{q}':")
        for r in results:
            print(f"  [{r['bm25_score']:.2f}] {r['content'][:80]}")
