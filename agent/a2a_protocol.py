#!/usr/bin/env python3
"""
🔗 A2A PROTOCOL — Agent-to-Agent Communication Bus.

Google AI Trend #2: «Agent2Agent (A2A) — open standard enabling 
seamless integration and orchestration between AI agents»

Лёгкая файловая шина для обмена сообщениями между агентами.
Каждый агент публикует/читает JSON-сообщения из shared mailbox.

Агенты:
- angelochka  — продажи, клиентский сервис
- avitolog    — Avito аудит и оптимизация
- scanner     — CRM сканер / забытые сделки
- reporter    — отчёты и KPI
- proactive   — проактивные действия

v1.0 — 15.04.2026
"""
import os
import json
import time
from datetime import datetime

MAILBOX_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "a2a_mailbox"
)
os.makedirs(MAILBOX_DIR, exist_ok=True)

INBOX_FILE = os.path.join(MAILBOX_DIR, "inbox.json")
LOG_FILE = os.path.join(MAILBOX_DIR, "a2a_log.json")


class AgentMessage:
    """Сообщение между агентами."""
    
    def __init__(self, sender: str, receiver: str, intent: str, 
                 payload: dict = None, priority: int = 3):
        self.id = f"{sender}_{int(time.time()*1000)}"
        self.sender = sender
        self.receiver = receiver
        self.intent = intent
        self.payload = payload or {}
        self.priority = priority  # 1=urgent, 5=low
        self.timestamp = datetime.now().isoformat()
        self.status = "pending"
    
    def to_dict(self):
        return {
            "id": self.id,
            "sender": self.sender,
            "receiver": self.receiver,
            "intent": self.intent,
            "payload": self.payload,
            "priority": self.priority,
            "timestamp": self.timestamp,
            "status": self.status
        }
    
    @classmethod
    def from_dict(cls, d):
        msg = cls(d["sender"], d["receiver"], d["intent"], 
                  d.get("payload", {}), d.get("priority", 3))
        msg.id = d.get("id", msg.id)
        msg.timestamp = d.get("timestamp", msg.timestamp)
        msg.status = d.get("status", "pending")
        return msg


class AgentBus:
    """Файловая шина обмена сообщениями."""
    
    def __init__(self):
        self._ensure_files()
    
    def _ensure_files(self):
        if not os.path.exists(INBOX_FILE):
            with open(INBOX_FILE, "w") as f:
                json.dump([], f)
        if not os.path.exists(LOG_FILE):
            with open(LOG_FILE, "w") as f:
                json.dump([], f)
    
    def _load_inbox(self) -> list:
        try:
            with open(INBOX_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    
    def _save_inbox(self, messages: list):
        with open(INBOX_FILE, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
    
    def publish(self, msg: AgentMessage):
        """Публикует сообщение в шину."""
        inbox = self._load_inbox()
        inbox.append(msg.to_dict())
        # Максимум 200 сообщений в inbox
        if len(inbox) > 200:
            inbox = inbox[-200:]
        self._save_inbox(inbox)
        
        # Логируем
        self._log_event("publish", msg)
        return msg.id
    
    def get_messages(self, agent_id: str, status: str = "pending") -> list:
        """Получает все сообщения для агента."""
        inbox = self._load_inbox()
        return [
            AgentMessage.from_dict(m) for m in inbox
            if m["receiver"] == agent_id and m["status"] == status
        ]
    
    def mark_read(self, message_id: str):
        """Помечает сообщение как прочитанное."""
        inbox = self._load_inbox()
        for m in inbox:
            if m["id"] == message_id:
                m["status"] = "read"
                break
        self._save_inbox(inbox)
    
    def mark_done(self, message_id: str, result: dict = None):
        """Помечает как выполненное с результатом."""
        inbox = self._load_inbox()
        for m in inbox:
            if m["id"] == message_id:
                m["status"] = "done"
                if result:
                    m["result"] = result
                break
        self._save_inbox(inbox)
    
    def get_stats(self) -> dict:
        """Статистика шины."""
        inbox = self._load_inbox()
        return {
            "total": len(inbox),
            "pending": sum(1 for m in inbox if m["status"] == "pending"),
            "read": sum(1 for m in inbox if m["status"] == "read"),
            "done": sum(1 for m in inbox if m["status"] == "done"),
            "by_sender": {sender: sum(1 for m in inbox if m["sender"] == sender) 
                         for sender in set(m["sender"] for m in inbox)},
        }
    
    def _log_event(self, event_type, msg):
        try:
            log = []
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    log = json.load(f)
            log.append({
                "event": event_type,
                "message_id": msg.id,
                "sender": msg.sender,
                "receiver": msg.receiver,
                "intent": msg.intent,
                "timestamp": datetime.now().isoformat()
            })
            # Максимум 500 записей лога
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(log[-500:], f, ensure_ascii=False, indent=2)
        except Exception:
            pass


# ============================================================
# CONVENIENCE FUNCTIONS (для быстрого использования из агентов)
# ============================================================

bus = AgentBus()

def notify(sender: str, receiver: str, message: str, data: dict = None, priority: int = 3):
    """Быстрая отправка уведомления между агентами.
    
    Примеры:
        notify("avitolog", "angelochka", "Объявление #42 неэффективно", {"item_id": 42})
        notify("scanner", "reporter", "3 забытые сделки", {"deals": [...]}, priority=1)
    """
    msg = AgentMessage(
        sender=sender,
        receiver=receiver,
        intent="notification",
        payload={"message": message, **(data or {})},
        priority=priority
    )
    return bus.publish(msg)


def request_data(sender: str, receiver: str, query: str, params: dict = None):
    """Запрос данных от другого агента."""
    msg = AgentMessage(
        sender=sender,
        receiver=receiver,
        intent="request_data",
        payload={"query": query, **(params or {})},
        priority=2
    )
    return bus.publish(msg)


def report_insight(sender: str, insight: str, data: dict = None):
    """Публикует инсайт для всех агентов (receiver='all')."""
    msg = AgentMessage(
        sender=sender,
        receiver="all",
        intent="insight",
        payload={"insight": insight, **(data or {})},
        priority=3
    )
    return bus.publish(msg)


def delegate_task(sender: str, receiver: str, task: str, params: dict = None):
    """Делегирует задачу другому агенту."""
    msg = AgentMessage(
        sender=sender,
        receiver=receiver,
        intent="delegate_task",
        payload={"task": task, **(params or {})},
        priority=2
    )
    return bus.publish(msg)
