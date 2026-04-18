#!/usr/bin/env python3
"""
🧠 CLIENT MEMORY — Модуль памяти о клиентах.

Анжелочка помнит каждого клиента:
- Имя, город
- Какие породы спрашивал / заказывал
- Суммы, даты
- Предпочтения
- LTV (суммарная выручка)

Google AI Trend #3: «Hi, Elizaveta. I see you're calling about the blue sweater.»

Использование:
    from client_memory import memory
    context = memory.recall("tg_123456")
    memory.remember("tg_123456", {"action": "запрос", "breed": "КОББ-500", "qty": 100})
"""
import os
import json
import re
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "clients")
os.makedirs(DATA_DIR, exist_ok=True)
MEMORY_FILE = os.path.join(DATA_DIR, "memory.json")


class ClientMemory:
    """Personalized memory for each client."""
    
    def __init__(self):
        self._data = self._load()
    
    def _load(self):
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
    
    def _save(self):
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
    
    def remember(self, client_id: str, interaction: dict):
        """Сохраняет факт взаимодействия.
        
        interaction = {
            "action": "запрос" | "заказ" | "жалоба" | "консультация",
            "breed": "КОББ-500",
            "qty": 100,
            "total": 8500,
            "city": "Симферополь",
            "name": "Марина",
            "notes": "Интересовалась доставкой"
        }
        """
        if client_id not in self._data:
            self._data[client_id] = {
                "name": None,
                "city": None,
                "phone": None,
                "history": [],
                "preferences": [],
                "ltv": 0,
                "first_contact": datetime.now().isoformat(),
                "last_contact": datetime.now().isoformat()
            }
        
        client = self._data[client_id]
        
        # Обновляем базовые данные
        if interaction.get("name"):
            client["name"] = interaction["name"]
        if interaction.get("city"):
            client["city"] = interaction["city"]
        if interaction.get("phone"):
            client["phone"] = interaction["phone"]
        
        # Добавляем событие
        event = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": datetime.now().strftime("%H:%M"),
            "action": interaction.get("action", "контакт")
        }
        if interaction.get("breed"):
            event["breed"] = interaction["breed"]
        if interaction.get("qty"):
            event["qty"] = interaction["qty"]
        if interaction.get("total"):
            event["total"] = interaction["total"]
            client["ltv"] = client.get("ltv", 0) + interaction["total"]
        if interaction.get("notes"):
            event["notes"] = interaction["notes"]
        
        client["history"].append(event)
        client["last_contact"] = datetime.now().isoformat()
        
        # Извлекаем предпочтения
        if interaction.get("breed"):
            breed = interaction["breed"].lower()
            prefs = client.get("preferences", [])
            if breed not in [p.lower() for p in prefs]:
                prefs.append(interaction["breed"])
                client["preferences"] = prefs[-5:]  # максимум 5
        
        self._save()
    
    def recall(self, client_id: str) -> str:
        """Возвращает текстовый контекст для промпта.
        
        Пример: 'Клиент Марина из Симферополя. 
        В марте заказывала 100 КОББ-500 (8500₽). 
        Интересовалась индюшатами. LTV: 8500₽.'
        """
        if client_id not in self._data:
            return ""
        
        client = self._data[client_id]
        parts = []
        
        name = client.get("name", "")
        city = client.get("city", "")
        if name:
            parts.append(f"Это {name}" + (f" из {city}" if city else ""))
        
        # Последние 3 взаимодействия
        history = client.get("history", [])[-3:]
        if history:
            for h in history:
                line = f"  {h.get('date', '?')}: {h.get('action', '?')}"
                if h.get("breed"):
                    line += f" — {h['breed']}"
                if h.get("qty"):
                    line += f" ({h['qty']} шт)"
                if h.get("total"):
                    line += f" на {h['total']}₽"
                parts.append(line)
        
        prefs = client.get("preferences", [])
        if prefs:
            parts.append(f"Предпочтения: {', '.join(prefs)}")
        
        ltv = client.get("ltv", 0)
        if ltv > 0:
            parts.append(f"Суммарно потратил(а): {ltv}₽")
        
        return "\n".join(parts) if parts else ""
    
    def extract_info_from_text(self, client_id: str, text: str, response: str):
        """Автоматически извлекает факты из диалога.
        
        Анализирует текст сообщения и ответ, чтобы запомнить:
        - Город (если упоминается)
        - Породу (если спрашивает)
        - Имя (если представляется)
        """
        interaction = {"action": "контакт"}
        text_lower = text.lower()
        
        # Извлечение пород
        breeds = [
            "кобб", "росс", "бройлер", "мулард", "индюк", "биг-6", "гус",
            "утк", "несуш", "ломан", "доминант", "master grey", "redbro",
            "агидель", "фаворит", "линд", "хайбрид", "конвертер", "бронз",
            "мясояич", "кучинск", "голошей", "хохлат", "хайсекс", "адлер"
        ]
        for breed in breeds:
            if breed in text_lower:
                interaction["breed"] = breed.capitalize()
                interaction["action"] = "запрос"
                break
        
        # Извлечение города
        cities = [
            "симферополь", "севастополь", "джанкой", "евпатория", "ялта",
            "феодосия", "керчь", "бахчисарай", "краснодар", "ростов",
            "волгоград", "крым", "москва", "сочи"
        ]
        for city in cities:
            if city in text_lower:
                interaction["city"] = city.capitalize()
                break
        
        # Извлечение количества
        qty_match = re.search(r'(\d+)\s*(шт|голов|штук|цыплят|птиц)', text_lower)
        if qty_match:
            interaction["qty"] = int(qty_match.group(1))
        
        # Извлечение имени (простое)
        name_match = re.search(r'меня зовут\s+(\w+)', text_lower)
        if name_match:
            interaction["name"] = name_match.group(1).capitalize()
        
        # Сохраняем только если нашли что-то полезное
        if len(interaction) > 1:  # больше чем просто "action"
            self.remember(client_id, interaction)
            return True
        return False
    
    def get_dormant_clients(self, days=30) -> list:
        """Находит клиентов, не обращавшихся N дней."""
        dormant = []
        now = datetime.now()
        for client_id, data in self._data.items():
            last = data.get("last_contact", "")
            if last:
                try:
                    last_dt = datetime.fromisoformat(last)
                    delta = (now - last_dt).days
                    if delta >= days:
                        dormant.append({
                            "id": client_id,
                            "name": data.get("name", "?"),
                            "days_silent": delta,
                            "ltv": data.get("ltv", 0),
                            "preferences": data.get("preferences", [])
                        })
                except Exception:
                    pass
        return sorted(dormant, key=lambda x: x["ltv"], reverse=True)


# Singleton instance
memory = ClientMemory()
