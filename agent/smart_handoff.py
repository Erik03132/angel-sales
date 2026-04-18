#!/usr/bin/env python3
"""
🤝 SMART HANDOFF — Умная передача сложных вопросов менеджеру.

Google AI Trend #3: «Smart handoff with a full summary 
for complex or emotionally charged issues»

Триггеры:
- Клиент 3+ раз переспросил (не понял)
- Негативный тон / жалоба
- Крупная сделка > 50 000₽
- Нестандартный запрос
- Вопрос по юридическим гарантиям

v1.0 — 15.04.2026
"""
import re


# Негативные паттерны
NEGATIVE_PATTERNS = [
    r'жало[бв]', r'ужас', r'обман', r'мошенник', r'верн[иу].*деньг',
    r'плохо[й]?\s+(качеств|обслуж)', r'претензи[яю]', r'адвокат',
    r'прокуратур', r'суд\b', r'роспотребнадзор', r'сдох',
    r'подох', r'пал[аи]', r'умер', r'не доех', r'обманываете'
]

# Юридические паттерны
LEGAL_PATTERNS = [
    r'гарант[иия]', r'договор', r'возврат', r'рекламаци',
    r'документ', r'ветсправк', r'сертификат', r'чек\b'
]

# Крупная сделка (> 50 000₽ или > 300 голов)
BIG_DEAL_PATTERNS = [
    r'(\d{3,})\s*(шт|голов|штук|цыплят|птиц|индюк|индюш|утят|гусят|муллард)',
    r'\b([5-9]\d{4,})\s*(руб|₽)',
    r'\b(партия|опт\b|крупный заказ|большой заказ)'
]


class SmartHandoff:
    """Детектор необходимости передачи менеджеру."""
    
    def __init__(self):
        self.repeat_counter = {}  # user_id -> count of unclear interactions
    
    def check(self, user_id: str, text: str, response: str, history: list = None) -> dict:
        """
        Проверяет, нужна ли передача менеджеру.
        
        Returns:
            None — если все ОК, агент справляется
            dict — если нужен handoff:
                {
                    "reason": "negative_tone" | "big_deal" | "legal" | "repeat" | "explicit",
                    "urgency": 1-5,
                    "summary": "Клиент жалуется на качество птицы...",
                    "recommendation": "Позвонить в течение 30 минут"
                }
        """
        text_lower = text.lower()
        
        # 1. ЯВНЫЙ ЗАПРОС МЕНЕДЖЕРА
        if any(p in text_lower for p in ['менеджер', 'оператор', 'человек', 'живой человек', 
                                          'позовите', 'переключите', 'начальник', 'руководител']):
            return {
                "reason": "explicit",
                "urgency": 2,
                "summary": f"Клиент прямо попросил связать с менеджером. Последний вопрос: '{text[:100]}'",
                "recommendation": "Перезвонить в течение 15 минут."
            }
        
        # 2. НЕГАТИВНЫЙ ТОН / ЖАЛОБА
        for pattern in NEGATIVE_PATTERNS:
            if re.search(pattern, text_lower):
                return {
                    "reason": "negative_tone",
                    "urgency": 1,  # Срочно!
                    "summary": f"🔴 Клиент жалуется/негативит: '{text[:150]}'",
                    "recommendation": "СРОЧНО позвонить! Извиниться, предложить компенсацию."
                }
        
        # 3. ЮРИДИЧЕСКИЕ ВОПРОСЫ
        for pattern in LEGAL_PATTERNS:
            if re.search(pattern, text_lower):
                return {
                    "reason": "legal",
                    "urgency": 3,
                    "summary": f"Клиент спрашивает о документах/гарантиях: '{text[:100]}'",
                    "recommendation": "Подготовить ветсправки и информацию о гарантиях."
                }
        
        # 4. КРУПНАЯ СДЕЛКА
        for pattern in BIG_DEAL_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                return {
                    "reason": "big_deal",
                    "urgency": 2,
                    "summary": f"💰 Потенциально крупная сделка: '{text[:150]}'",
                    "recommendation": "Позвонить, предложить индивидуальные условия и скидку за объём."
                }
        
        # 5. ПОВТОРНЫЕ ВОПРОСЫ (клиент не понял)
        if history and len(history) >= 6:
            # Считаем количество вопросительных сообщений подряд
            recent_questions = 0
            for msg in history[-6:]:
                if msg.get("role") == "user":
                    user_text = msg.get("parts", [""])[0] if isinstance(msg.get("parts"), list) else ""
                    if '?' in user_text or any(w in user_text.lower() for w in ['не понял', 'повтори', 'а что', 'как это', 'не ясно']):
                        recent_questions += 1
            
            if recent_questions >= 3:
                return {
                    "reason": "repeat",
                    "urgency": 3,
                    "summary": f"Клиент переспрашивает 3+ раза — скорее всего не понимает объяснения AI.",
                    "recommendation": "Позвонить и объяснить голосом."
                }
        
        return None  # Всё ОК, handoff не нужен
    
    def format_handoff_message(self, handoff: dict, user_name: str = "Клиент", 
                                client_context: str = "") -> str:
        """Форматирует сообщение для передачи менеджеру."""
        
        urgency_icons = {1: "🔴 СРОЧНО", 2: "🟡 ВАЖНО", 3: "🟢 ОБЫЧНОЕ"}
        urgency_label = urgency_icons.get(handoff["urgency"], "📋")
        
        lines = [
            f"📋 ПЕРЕДАЧА МЕНЕДЖЕРУ | {urgency_label}",
            f"",
            f"👤 {user_name}",
        ]
        
        if client_context:
            lines.append(f"📝 {client_context}")
        
        lines.extend([
            f"",
            f"📌 Причина: {handoff['reason']}",
            f"💬 {handoff['summary']}",
            f"",
            f"⚡ {handoff['recommendation']}"
        ])
        
        return "\n".join(lines)


# Singleton
handoff_detector = SmartHandoff()
