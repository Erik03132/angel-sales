import os

from dotenv import load_dotenv
from psycopg2 import pool
from psycopg2.extras import Json, RealDictCursor

load_dotenv()
if not os.getenv("GEMINI_API_KEY"):
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# --- Lazy-import FastEmbed (локально, без API) ---
_embedder = None

EMBED_DIM = 384
EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def _get_embedder():
    global _embedder
    if _embedder is None:
        from fastembed import TextEmbedding
        _embedder = TextEmbedding(EMBED_MODEL)
    return _embedder


class AngelochkaVectorDB:
    def __init__(self):
        self.db_url = os.getenv("NEON_DATABASE_URL")
        self.enabled = self.db_url is not None
        self.connection_pool = None
        if self.enabled:
            self._init_db()

    def _init_db(self):
        try:
            self.connection_pool = pool.SimpleConnectionPool(1, 5, self.db_url)
            conn = self._get_valid_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS angelochka_knowledge (
                            id SERIAL PRIMARY KEY,
                            content TEXT,
                            metadata JSONB,
                            embedding vector({EMBED_DIM})
                        );
                    """)
                    conn.commit()
            finally:
                self.connection_pool.putconn(conn)
            print(f"✅ Neon VectorDB: пул инициализирован (embedding dim={EMBED_DIM})")
        except Exception as e:
            print(f"❌ Ошибка инициализации Neon DB: {e}")
            self.enabled = False

    def _get_valid_conn(self):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                conn = self.connection_pool.getconn()
                conn.isolation_level
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                return conn
            except Exception:
                try:
                    self.connection_pool.putconn(conn, close=True)
                except Exception:
                    pass
                if attempt == max_retries - 1:
                    try:
                        self.connection_pool.closeall()
                    except Exception:
                        pass
                    self.connection_pool = pool.SimpleConnectionPool(1, 5, self.db_url)
                    return self.connection_pool.getconn()
        return self.connection_pool.getconn()

    def health_check(self):
        if not self.enabled:
            return False
        try:
            conn = self._get_valid_conn()
            self.connection_pool.putconn(conn)
            return True
        except Exception:
            return False

    def get_embedding(self, text: str):
        embedder = _get_embedder()
        emb = list(embedder.embed(text))[0]
        return emb.tolist()

    def add_knowledge(self, text: str, meta: dict):
        if not self.enabled:
            return
        conn = None
        try:
            embedding = self.get_embedding(text)
            conn = self._get_valid_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO angelochka_knowledge (content, metadata, embedding) VALUES (%s, %s, %s)",
                    (text, Json(meta), embedding)
                )
                conn.commit()
        except Exception as e:
            print(f"❌ Ошибка при добавлении знаний: {e}")
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
        finally:
            if conn:
                try:
                    self.connection_pool.putconn(conn)
                except Exception:
                    pass

    def search(self, query: str, limit=3):
        if not self.enabled:
            return []
        conn = None
        try:
            query_embedding = self.get_embedding(query)
            conn = self._get_valid_conn()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT content, metadata, 1 - (embedding <=> %s::vector) as similarity FROM angelochka_knowledge ORDER BY similarity DESC LIMIT %s",
                    (query_embedding, limit)
                )
                return cur.fetchall()
        except Exception as e:
            print(f"❌ Ошибка при поиске: {e}")
            return []
        finally:
            if conn:
                try:
                    self.connection_pool.putconn(conn)
                except Exception:
                    pass
