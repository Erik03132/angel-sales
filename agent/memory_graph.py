#!/usr/bin/env python3
"""
memory_graph.py — Граф памяти клиентов (TAU15 + SQLite).

Адаптация подхода «Вселенная воспоминаний» под бизнес VezemCip.
Три роли: Библиотекарь (схема), Детектив (анализ), Редактор (архивация).

Связан с:
- knowledge/library/tau15-memory-graph.md
- knowledge/agent-memory-architecture/ (SQLite решение)
- kulibin-engineer/SKILL.md → Gemini Embedding 2, Binary Quantization
"""

import json
import os
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "client_memory.db")


class MemoryGraph:
    """Семантический граф памяти клиентов.

    Каждый клиент — набор узлов (facts, preferences, intents, deals)
    связанных рёбрами (because, leads_to, contradicts, bought_with).

    Hub (val >= 25): ядро — имя, город, основной запрос.
    Detail (val < 25): детали — конкретные породы, цены, даты.
    Heat: свежесть факта (decay 0.95/день).
    """

    SCHEMA_MUST = ["chat_id", "node_id", "name", "node_type", "formed_at"]
    SCHEMA_OPT = ["summary", "tags", "confidence", "cluster_id", "icon", "color", "val"]
    NODE_TYPES = {"fact", "preference", "intent", "deal", "conflict", "contact"}
    RELATIONS = {"because", "leads_to", "contradicts", "bought_with", "prefers_over", "located_in"}

    def __init__(self, db_path: str = DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        """Библиотекарь: жёсткая схема — закон."""
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS memory_nodes (
                node_id     TEXT PRIMARY KEY,
                chat_id     TEXT NOT NULL,
                name        TEXT NOT NULL,
                node_type   TEXT NOT NULL DEFAULT 'fact',
                summary     TEXT,
                tags        TEXT,
                confidence  REAL DEFAULT 0.8,
                val         INTEGER DEFAULT 10,
                heat        REAL DEFAULT 1.0,
                cluster_id  TEXT,
                is_forgotten INTEGER DEFAULT 0,
                is_scar     INTEGER DEFAULT 0,
                formed_at   INTEGER NOT NULL,
                icon        TEXT,
                color       TEXT
            );

            CREATE TABLE IF NOT EXISTS memory_edges (
                from_id     TEXT NOT NULL,
                to_id       TEXT NOT NULL,
                relation    TEXT NOT NULL,
                weight      REAL DEFAULT 1.0,
                formed_at   INTEGER,
                PRIMARY KEY (from_id, to_id, relation)
            );

            CREATE INDEX IF NOT EXISTS idx_nodes_chat ON memory_nodes(chat_id);
            CREATE INDEX IF NOT EXISTS idx_nodes_type ON memory_nodes(node_type);
            CREATE INDEX IF NOT EXISTS idx_nodes_heat ON memory_nodes(heat DESC);
            CREATE INDEX IF NOT EXISTS idx_nodes_active ON memory_nodes(is_forgotten);
            CREATE INDEX IF NOT EXISTS idx_edges_from ON memory_edges(from_id);
            CREATE INDEX IF NOT EXISTS idx_edges_to ON memory_edges(to_id);
        """)
        self.db.commit()

    # ─── Библиотекарь: чтение ──────────────────────────────────────

    def get_nodes(self, chat_id: str, include_forgotten: bool = False) -> list[dict]:
        """Все узлы клиента, отсортированные по val*heat (самое важное сверху)."""
        q = "SELECT * FROM memory_nodes WHERE chat_id = ?"
        if not include_forgotten:
            q += " AND is_forgotten = 0"
        q += " ORDER BY (val * heat) DESC"
        rows = self.db.execute(q, (chat_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_hubs(self, chat_id: str) -> list[dict]:
        """Только хабы (val >= 25) — ядро клиента."""
        rows = self.db.execute(
            "SELECT * FROM memory_nodes WHERE chat_id = ? AND val >= 25 AND is_forgotten = 0 ORDER BY val DESC",
            (chat_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_details(self, hub_id: str) -> list[dict]:
        """Детали привязанные к хабу."""
        rows = self.db.execute(
            "SELECT * FROM memory_nodes WHERE cluster_id = ? AND is_forgotten = 0 ORDER BY heat DESC",
            (hub_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_edges(self, node_id: str) -> list[dict]:
        """Все связи узла (исходящие + входящие)."""
        rows = self.db.execute(
            "SELECT * FROM memory_edges WHERE from_id = ? OR to_id = ?",
            (node_id, node_id)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_memory_map(self, chat_id: str) -> dict:
        """Компактная карта памяти для передачи в LLM."""
        hubs = self.get_hubs(chat_id)
        result = {"chat_id": chat_id, "hubs": []}
        for hub in hubs:
            hub_data = {
                "node_id": hub["node_id"],
                "name": hub["name"],
                "type": hub["node_type"],
                "val": hub["val"],
                "heat": round(hub["heat"], 2),
                "tags": json.loads(hub["tags"]) if hub["tags"] else [],
                "details": [],
                "edges": []
            }
            for detail in self.get_details(hub["node_id"]):
                hub_data["details"].append({
                    "node_id": detail["node_id"],
                    "name": detail["name"],
                    "type": detail["node_type"],
                    "is_scar": bool(detail["is_scar"])
                })
            for edge in self.get_edges(hub["node_id"]):
                hub_data["edges"].append({
                    "from": edge["from_id"],
                    "to": edge["to_id"],
                    "relation": edge["relation"]
                })
            result["hubs"].append(hub_data)
        return result

    # ─── Детектив: запись ───────────────────────────────────────────

    def add_node(self, chat_id: str, node_id: str, name: str,
                 node_type: str = "fact", summary: str = None,
                 tags: list = None, val: int = 10, cluster_id: str = None,
                 confidence: float = 0.8) -> str:
        """Добавляет узел в граф. Возвращает node_id."""
        if node_type not in self.NODE_TYPES:
            raise ValueError(f"node_type '{node_type}' не в {self.NODE_TYPES}")

        self.db.execute("""
            INSERT OR REPLACE INTO memory_nodes
            (node_id, chat_id, name, node_type, summary, tags, confidence, val, heat, cluster_id, formed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1.0, ?, ?)
        """, (
            node_id, chat_id, name, node_type, summary,
            json.dumps(tags or [], ensure_ascii=False),
            confidence, val, cluster_id, int(time.time())
        ))
        self.db.commit()
        return node_id

    def add_edge(self, from_id: str, to_id: str, relation: str, weight: float = 1.0):
        """Создаёт связь между узлами."""
        if relation not in self.RELATIONS:
            raise ValueError(f"relation '{relation}' не в {self.RELATIONS}")

        self.db.execute("""
            INSERT OR REPLACE INTO memory_edges (from_id, to_id, relation, weight, formed_at)
            VALUES (?, ?, ?, ?, ?)
        """, (from_id, to_id, relation, weight, int(time.time())))
        self.db.commit()

    # ─── Редактор: архивация и шрамы ────────────────────────────────

    def archive_node(self, node_id: str):
        """Архивирует узел (is_forgotten=1). Не удаляет — история."""
        self.db.execute(
            "UPDATE memory_nodes SET is_forgotten = 1 WHERE node_id = ?",
            (node_id,)
        )
        self.db.commit()

    def mark_scar(self, node_id: str):
        """Помечает конфликт/противоречие."""
        self.db.execute(
            "UPDATE memory_nodes SET is_scar = 1, node_type = 'conflict' WHERE node_id = ?",
            (node_id,)
        )
        self.db.commit()

    def decay_heat(self, factor: float = 0.95):
        """Ежедневный decay — старые факты 'остывают'. Запускать по cron."""
        self.db.execute(
            "UPDATE memory_nodes SET heat = MAX(heat * ?, 0.01) WHERE is_forgotten = 0",
            (factor,)
        )
        self.db.commit()

    def warm_up(self, node_id: str, boost: float = 1.0):
        """Подогреть узел при упоминании клиентом."""
        self.db.execute(
            "UPDATE memory_nodes SET heat = MIN(heat + ?, 1.0) WHERE node_id = ?",
            (boost, node_id)
        )
        self.db.commit()

    # ─── Статистика ─────────────────────────────────────────────────

    def stats(self) -> dict:
        """Статистика по базе."""
        nodes = self.db.execute("SELECT COUNT(*) FROM memory_nodes WHERE is_forgotten=0").fetchone()[0]
        forgotten = self.db.execute("SELECT COUNT(*) FROM memory_nodes WHERE is_forgotten=1").fetchone()[0]
        scars = self.db.execute("SELECT COUNT(*) FROM memory_nodes WHERE is_scar=1").fetchone()[0]
        edges = self.db.execute("SELECT COUNT(*) FROM memory_edges").fetchone()[0]
        clients = self.db.execute("SELECT COUNT(DISTINCT chat_id) FROM memory_nodes").fetchone()[0]
        return {
            "active_nodes": nodes,
            "archived": forgotten,
            "scars": scars,
            "edges": edges,
            "unique_clients": clients
        }

    def close(self):
        self.db.close()


# ─── Demo: заполнение тестовыми данными ─────────────────────────────

def demo():
    """Демо: клиент Иван из Армавира."""
    mg = MemoryGraph()

    # Hub: клиент
    mg.add_node("client_ivan", "ivan_hub", "Иван (Армавир)",
                node_type="contact", val=80,
                tags=["армавир", "бройлер", "постоянный"],
                summary="Клиент из Армавира, чувствителен к цене")

    # Detail: первый запрос
    mg.add_node("client_ivan", "ivan_kobb", "Спрашивал Кобб-500 × 200шт",
                node_type="intent", val=15, cluster_id="ivan_hub",
                tags=["кобб-500", "бройлер"])

    # Detail: отказ (шрам)
    mg.add_node("client_ivan", "ivan_refuse", "Отказался — дорого (90₽)",
                node_type="conflict", val=10, cluster_id="ivan_hub",
                tags=["отказ", "цена"])
    mg.mark_scar("ivan_refuse")

    # Detail: купил альтернативу
    mg.add_node("client_ivan", "ivan_ross", "Купил Росс-308 × 100шт (85₽)",
                node_type="deal", val=20, cluster_id="ivan_hub",
                tags=["росс-308", "бройлер", "сделка"])

    # Detail: доставка
    mg.add_node("client_ivan", "ivan_delivery", "Доставка: Армавир, ул. Ленина, 76",
                node_type="fact", val=10, cluster_id="ivan_hub",
                tags=["армавир", "доставка"])

    # Связи
    mg.add_edge("ivan_kobb", "ivan_refuse", "leads_to")
    mg.add_edge("ivan_refuse", "ivan_ross", "leads_to")
    mg.add_edge("ivan_ross", "ivan_kobb", "prefers_over")
    mg.add_edge("ivan_hub", "ivan_delivery", "located_in")

    # Вывод
    print("📊 Статистика:", mg.stats())
    print()

    memory = mg.get_memory_map("client_ivan")
    print("🧠 Карта памяти клиента:")
    print(json.dumps(memory, indent=2, ensure_ascii=False))

    mg.close()


if __name__ == "__main__":
    demo()
