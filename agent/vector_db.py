import os
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from psycopg2 import pool
from dotenv import load_dotenv

# Загружаем настройки из локального .env
load_dotenv()

# Если ключей нет локально, пробуем найти их в родительской папке (для совместимости)
if not os.getenv("GEMINI_API_KEY"):
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))


# --- Lazy-import Gemini (может упасть без прокси) ---
_genai = None
def _get_genai():
    global _genai
    if _genai is None:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        _genai = genai
    return _genai


class AngelochkaVectorDB:
    def __init__(self):
        self.db_url = os.getenv("NEON_DATABASE_URL")
        self.enabled = self.db_url is not None
        self.connection_pool = None
        if self.enabled:
            self._init_db()

    def _init_db(self):
        try:
            # Создаем пул соединений (от 1 до 5)
            self.connection_pool = pool.SimpleConnectionPool(1, 5, self.db_url)
            
            conn = self._get_valid_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS angelochka_knowledge (
                            id SERIAL PRIMARY KEY,
                            content TEXT,
                            metadata JSONB,
                            embedding vector(3072)
                        );
                    """)
                    conn.commit()
            finally:
                self.connection_pool.putconn(conn)
            print("✅ Neon VectorDB: пул инициализирован")
        except Exception as e:
            print(f"❌ Ошибка инициализации Neon DB: {e}")
            self.enabled = False

    def _get_valid_conn(self):
        """Получить валидное соединение из пула с авто-переподключением"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                conn = self.connection_pool.getconn()
                # Проверяем, что соединение живое
                conn.isolation_level  # Простой пинг
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                return conn
            except Exception:
                # Соединение битое — убиваем и берём новое
                try:
                    self.connection_pool.putconn(conn, close=True)
                except Exception:
                    pass
                if attempt == max_retries - 1:
                    # Пересоздаём весь пул
                    try:
                        self.connection_pool.closeall()
                    except Exception:
                        pass
                    self.connection_pool = pool.SimpleConnectionPool(1, 5, self.db_url)
                    return self.connection_pool.getconn()
        return self.connection_pool.getconn()

    def health_check(self):
        """Проверка готовности базы и API"""
        if not self.enabled: return False
        try:
            conn = self._get_valid_conn()
            self.connection_pool.putconn(conn)
            return True
        except Exception:
            return False

    def get_embedding(self, text: str):
        genai = _get_genai()
        result = genai.embed_content(
            model="models/gemini-embedding-2-preview",
            content=text,
            task_type="retrieval_document"
        )
        return result['embedding']

    def add_knowledge(self, text: str, meta: dict):
        if not self.enabled: return
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
                try: conn.rollback()
                except: pass
        finally:
            if conn:
                try: self.connection_pool.putconn(conn)
                except: pass

    def search(self, query: str, limit=3):
        if not self.enabled: return []
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
                try: self.connection_pool.putconn(conn)
                except: pass
