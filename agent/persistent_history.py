#!/usr/bin/env python3
"""
💾 PERSISTENT HISTORY — История диалогов в Neon PostgreSQL.

Анжелочка помнит контекст разговора даже после перезапуска бота.
Хранит последние N сообщений каждого клиента в облачной БД.

Использование:
    from persistent_history import chat_db
    
    # Загрузить историю при старте диалога
    history = chat_db.load_history(user_id=123456)
    
    # Сохранить после каждого обмена
    chat_db.save_message(user_id=123456, role="user", content="Сколько стоит Кобб?")
    chat_db.save_message(user_id=123456, role="model", content="90₽ за штуку!")
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# База данных
NEON_DATABASE_URL = os.getenv("NEON_DATABASE_URL")

# Конфигурация
MAX_HISTORY_PER_USER = 20      # Хранить последние N сообщений
HISTORY_TTL_DAYS = 30           # Удалять историю старше N дней
MAX_MESSAGE_LENGTH = 4000       # Обрезать слишком длинные сообщения


class PersistentHistory:
    """Облачное хранилище истории диалогов в Neon PostgreSQL."""
    
    def __init__(self):
        self._initialized = False
        self._available = bool(NEON_DATABASE_URL)
        if self._available:
            self._ensure_table()
    
    def _get_conn(self):
        """Получить соединение с БД."""
        import psycopg2
        return psycopg2.connect(NEON_DATABASE_URL)
    
    def _ensure_table(self):
        """Создать таблицу если не существует."""
        if self._initialized or not self._available:
            return
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    user_name TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                
                CREATE INDEX IF NOT EXISTS idx_chat_history_user_id 
                    ON chat_history(user_id);
                    
                CREATE INDEX IF NOT EXISTS idx_chat_history_created_at 
                    ON chat_history(created_at);
            """)
            conn.commit()
            cur.close()
            conn.close()
            self._initialized = True
            logger.info("✅ PersistentHistory: таблица chat_history готова")
        except Exception as e:
            logger.warning(f"⚠️ PersistentHistory: не удалось создать таблицу: {e}")
            self._available = False
    
    def save_message(self, user_id: int, role: str, content: str, user_name: str = None):
        """Сохранить сообщение в БД.
        
        Args:
            user_id: Telegram user ID
            role: 'user' или 'model'
            content: Текст сообщения
            user_name: Имя пользователя (опционально)
        """
        if not self._available:
            return
        
        # Обрезаем слишком длинные сообщения
        if len(content) > MAX_MESSAGE_LENGTH:
            content = content[:MAX_MESSAGE_LENGTH] + "..."
        
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO chat_history (user_id, user_name, role, content) 
                   VALUES (%s, %s, %s, %s)""",
                (user_id, user_name, role, content)
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            logger.warning(f"⚠️ PersistentHistory save error: {e}")
    
    def load_history(self, user_id: int, limit: int = None) -> List[Dict]:
        """Загрузить историю диалога из БД.
        
        Возвращает список в формате aiogram/Gemini:
        [{"role": "user", "parts": ["текст"]}, {"role": "model", "parts": ["текст"]}]
        
        Args:
            user_id: Telegram user ID
            limit: Макс. количество сообщений (по умолчанию MAX_HISTORY_PER_USER)
        
        Returns:
            Список сообщений в формате Gemini
        """
        if not self._available:
            return []
        
        if limit is None:
            limit = MAX_HISTORY_PER_USER
        
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute(
                """SELECT role, content FROM chat_history 
                   WHERE user_id = %s 
                   ORDER BY created_at DESC 
                   LIMIT %s""",
                (user_id, limit)
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
            
            # Разворачиваем (были DESC, нужен хронологический порядок)
            rows.reverse()
            
            history = []
            for role, content in rows:
                history.append({"role": role, "parts": [content]})
            
            return history
            
        except Exception as e:
            logger.warning(f"⚠️ PersistentHistory load error: {e}")
            return []
    
    def get_summary(self, user_id: int) -> str:
        """Получить краткую сводку о клиенте из истории.
        
        Возвращает строку: 'Клиент (ID: 123) — 15 сообщений за 7 дней. 
        Последний контакт: 2ч назад.'
        """
        if not self._available:
            return ""
        
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute(
                """SELECT 
                       COUNT(*) as msg_count,
                       MIN(created_at) as first_msg,
                       MAX(created_at) as last_msg,
                       MAX(user_name) as name
                   FROM chat_history 
                   WHERE user_id = %s""",
                (user_id,)
            )
            row = cur.fetchone()
            cur.close()
            conn.close()
            
            if not row or row[0] == 0:
                return ""
            
            msg_count, first_msg, last_msg, name = row
            
            # Рассчитываем давно ли последний контакт
            now = datetime.utcnow()
            delta = now - last_msg
            if delta.days > 0:
                ago = f"{delta.days} дн. назад"
            elif delta.seconds > 3600:
                ago = f"{delta.seconds // 3600}ч назад"
            else:
                ago = "недавно"
            
            name_str = f" ({name})" if name else ""
            return f"Постоянный клиент{name_str} — {msg_count} сообщ., последний контакт: {ago}."
            
        except Exception as e:
            logger.warning(f"⚠️ PersistentHistory summary error: {e}")
            return ""
    
    def cleanup_old(self, days: int = None):
        """Удалить старые записи (вызывать из scheduler)."""
        if not self._available:
            return 0
        
        if days is None:
            days = HISTORY_TTL_DAYS
        
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute(
                """DELETE FROM chat_history 
                   WHERE created_at < NOW() - INTERVAL '%s days'""",
                (days,)
            )
            deleted = cur.rowcount
            conn.commit()
            cur.close()
            conn.close()
            
            if deleted > 0:
                logger.info(f"🧹 PersistentHistory: удалено {deleted} старых записей")
            return deleted
            
        except Exception as e:
            logger.warning(f"⚠️ PersistentHistory cleanup error: {e}")
            return 0
    
    def trim_user_history(self, user_id: int, keep: int = None):
        """Оставить только последние N сообщений для пользователя."""
        if not self._available:
            return
        
        if keep is None:
            keep = MAX_HISTORY_PER_USER
        
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute(
                """DELETE FROM chat_history 
                   WHERE user_id = %s 
                   AND id NOT IN (
                       SELECT id FROM chat_history 
                       WHERE user_id = %s 
                       ORDER BY created_at DESC 
                       LIMIT %s
                   )""",
                (user_id, user_id, keep)
            )
            deleted = cur.rowcount
            conn.commit()
            cur.close()
            conn.close()
            
            if deleted > 0:
                logger.info(f"✂️ PersistentHistory: обрезано {deleted} сообщ. для user {user_id}")
                
        except Exception as e:
            logger.warning(f"⚠️ PersistentHistory trim error: {e}")
    
    def stats(self) -> dict:
        """Статистика БД для /status команды."""
        if not self._available:
            return {"available": False}
        
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute("""
                SELECT 
                    COUNT(*) as total_messages,
                    COUNT(DISTINCT user_id) as unique_users,
                    MAX(created_at) as last_activity
                FROM chat_history
            """)
            row = cur.fetchone()
            cur.close()
            conn.close()
            
            return {
                "available": True,
                "total_messages": row[0],
                "unique_users": row[1],
                "last_activity": str(row[2]) if row[2] else "never"
            }
        except Exception as e:
            return {"available": False, "error": str(e)}


# Singleton
chat_db = PersistentHistory()
