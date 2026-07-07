# x.ai Voice Agent — Pilot Plan

> **Цель:** Протестировать x.ai Voice Agent на 10 звонках, сравнить с baresip

## Архитектура пилота

```
┌─────────────────┐     ┌─────────┐     ┌──────────────────┐
│ auto_call_pilot.py│ ──→ │  Mango  │ ──→ │  x.ai Voice API  │
│ (новый скрипт)   │     │ Office  │     │  (Grok Voice)    │
└─────────────────┘     └─────────┘     │  WebSocket       │
                                        │  $0.05/мин       │
                                        └───────┬──────────┘
                                                │
                                        ┌───────▼───────┐
                                        │ Function Calls │
                                        │ → Bitrix24     │
                                        │ → Telegram     │
                                        └───────────────┘
```

## Файлы

| Файл | Назначение |
|------|-----------|
| `ai-eggs/agent/xai_voice_agent.py` | Клиент x.ai Voice API |
| `ai-eggs/agent/auto_call_pilot.py` | Пилотный обзвон (сравнение) |
| `ai-eggs/agent/pilot_results.py` | Сбор и анализ результатов |

## Этапы

### Этап 1: x.ai клиент (30 мин)

**Задача:** Создать WebSocket клиент для x.ai Voice Agent

```python
# xai_voice_agent.py

import websockets
import json
import asyncio
from typing import Callable, Optional

class XAIVoiceAgent:
    """Клиент x.ai Voice Agent API"""
    
    def __init__(self, api_key: str, instructions: str):
        self.api_key = api_key
        self.instructions = instructions
        self.ws = None
        self.tools = []
        
    async def connect(self):
        """Подключиться к x.ai WebSocket"""
        self.ws = await websockets.connect(
            "wss://api.x.ai/v1/realtime?model=grok-voice-latest",
            additional_headers={"Authorization": f"Bearer {self.api_key}"}
        )
        
        # Настроить сессию
        await self.ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "instructions": self.instructions,
                "tools": self.tools,
                "voice": "alloy"  # или другой голос
            }
        }))
        
    async def send_audio(self, audio_data: bytes):
        """Отправить аудио"""
        await self.ws.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": audio_data.hex()
        }))
        
    async def receive_audio(self) -> Optional[bytes]:
        """Получить аудио ответ"""
        async for message in self.ws:
            data = json.loads(message)
            if data["type"] == "response.audio.delta":
                return bytes.fromhex(data["delta"])
            elif data["type"] == "response.function_call_arguments.done":
                # Обработать function call
                await self.handle_function_call(data)
        return None
    
    async def handle_function_call(self, data: dict):
        """Обработать вызов функции"""
        func_name = data["name"]
        args = json.loads(data["arguments"])
        
        if func_name == "confirm_order":
            # Логика подтверждения
            pass
        elif func_name == "schedule_callback":
            # Логика повторного звонка
            pass
        
        # Отправить результат
        await self.ws.send(json.dumps({
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": data["call_id"],
                "output": json.dumps({"success": True})
            }
        }))
```

### Этап 2: Пилотный скрипт (45 мин)

**Задача:** Создать скрипт для сравнения baresip vs x.ai

```python
# auto_call_pilot.py

import asyncio
import json
import time
from datetime import datetime
from typing import List, Dict
from dataclasses import dataclass

@dataclass
class PilotResult:
    """Результат пилотного звонка"""
    phone: str
    method: str  # "baresip" или "xai"
    duration_sec: float
    outcome: str  # "connected", "no_answer", "busy", "confirmed", "rejected"
    transcript: str
    cost: float
    timestamp: str

class PilotRunner:
    """Запуск пилотных звонков"""
    
    def __init__(self):
        self.results: List[PilotResult] = []
        
    async def run_baresip_call(self, phone: str, script: str) -> PilotResult:
        """Звонок через baresip (текущий метод)"""
        start = time.time()
        
        # Инициировать звонок через Mango
        from auto_confirm_call import make_call
        await make_call(phone)
        
        # Ждать завершения
        await asyncio.sleep(30)  # Макс 30 сек
        
        duration = time.time() - start
        
        return PilotResult(
            phone=phone,
            method="baresip",
            duration_sec=duration,
            outcome="connected",  # Упрощено
            transcript="",
            cost=0.0,
            timestamp=datetime.now().isoformat()
        )
    
    async def run_xai_call(self, phone: str, instructions: str) -> PilotResult:
        """Звонок через x.ai Voice Agent"""
        start = time.time()
        
        from xai_voice_agent import XAIVoiceAgent
        
        agent = XAIVoiceAgent(
            api_key="YOUR_XAI_API_KEY",
            instructions=instructions
        )
        
        await agent.connect()
        
        # TODO: Связать с Mango SIP
        # Пока что заглушка
        
        duration = time.time() - start
        
        return PilotResult(
            phone=phone,
            method="xai",
            duration_sec=duration,
            outcome="connected",
            transcript="",
            cost=duration / 60 * 0.05,  # $0.05/мин
            timestamp=datetime.now().isoformat()
        )
    
    async def run_comparison(self, phones: List[str]):
        """Запуск сравнительного теста"""
        print("=" * 60)
        print("PILOT: baresip vs x.ai Voice Agent")
        print("=" * 60)
        
        for i, phone in enumerate(phones):
            print(f"\n📞 Звонок {i+1}/{len(phones)}: {phone}")
            
            # Чередуем методы
            if i % 2 == 0:
                result = await self.run_baresip_call(phone, "")
            else:
                result = await self.run_xai_call(phone, self.get_instructions())
            
            self.results.append(result)
            print(f"   Результат: {result.outcome} | Стоимость: ${result.cost:.2f}")
            
            # Пауза между звонками
            await asyncio.sleep(5)
        
        self.print_summary()
    
    def get_instructions(self) -> str:
        """Инструкции для x.ai агента"""
        return """
        Ты — менеджер компании "Подворье".
        Ты звонишь клиенту для подтверждения заказа.
        
        Сценарий:
        1. Поприветствуй: "Здравствуйте! Это менеджер компании Подворье."
        2. Спроси: "Вы делали заказ у нас? Хотите его подтвердить?"
        3. Если ДА: "Отлично! Ваш заказ будет доставлен завтра."
        4. Если НЕТ: "Хорошо, извините за беспокойство."
        5. Если ВОПРОС: "Давайте я вам перезвоню позже."
        
        Говори кратко, по-русски, дружелюбно.
        """
    
    def print_summary(self):
        """Вывести сводку"""
        print("\n" + "=" * 60)
        print("СВОДКА ПИЛОТА")
        print("=" * 60)
        
        baresip_results = [r for r in self.results if r.method == "baresip"]
        xai_results = [r for r in self.results if r.method == "xai"]
        
        print(f"\nbaresip: {len(baresip_results)} звонков")
        print(f"  Среднее время: {sum(r.duration_sec for r in baresip_results) / max(len(baresip_results), 1):.1f} сек")
        print(f"  Стоимость: ${sum(r.cost for r in baresip_results):.2f}")
        
        print(f"\nx.ai: {len(xai_results)} звонков")
        print(f"  Среднее время: {sum(r.duration_sec for r in xai_results) / max(len(xai_results), 1):.1f} сек")
        print(f"  Стоимость: ${sum(r.cost for r in xai_results):.2f}")
        
        # Сохранить результаты
        with open("pilot_results.json", "w") as f:
            json.dump([vars(r) for r in self.results], f, indent=2)
        
        print("\nРезультаты сохранены в pilot_results.json")
```

### Этап 3: Сбор результатов (15 мин)

**Задача:** Скрипт для анализа результатов пилота

```python
# pilot_results.py

import json
import pandas as pd
from pathlib import Path

def analyze_pilot():
    """Анализ результатов пилота"""
    
    results_file = Path("pilot_results.json")
    if not results_file.exists():
        print("Нет данных для анализа")
        return
    
    with open(results_file) as f:
        data = json.load(f)
    
    df = pd.DataFrame(data)
    
    print("=" * 60)
    print("АНАЛИЗ ПИЛОТА: baresip vs x.ai")
    print("=" * 60)
    
    # Конверсия
    print("\n📊 Конверсия:")
    for method in ["baresip", "xai"]:
        method_df = df[df["method"] == method]
        total = len(method_df)
        confirmed = len(method_df[method_df["outcome"] == "confirmed"])
        print(f"  {method}: {confirmed}/{total} ({confirmed/max(total,1)*100:.1f}%)")
    
    # Стоимость
    print("\n💰 Стоимость:")
    for method in ["baresip", "xai"]:
        method_df = df[df["method"] == method]
        print(f"  {method}: ${method_df['cost'].sum():.2f}")
    
    # Средняя длительность
    print("\n⏱️ Средняя длительность:")
    for method in ["baresip", "xai"]:
        method_df = df[df["method"] == method]
        print(f"  {method}: {method_df['duration_sec'].mean():.1f} сек")
    
    # Рекомендация
    print("\n" + "=" * 60)
    print("РЕКОМЕНДАЦИЯ")
    print("=" * 60)
    
    xai_cost = df[df["method"] == "xai"]["cost"].sum()
    baresip_cost = df[df["method"] == "baresip"]["cost"].sum()
    
    if xai_cost < baresip_cost * 1.5:  # x.ai дороже не более чем на 50%
        print("✅ x.ai рекомендуется для пилота")
    else:
        print("⚠️ x.ai значительно дороже, рассмотреть гибрид")
```

## Запуск пилота

```bash
# 1. Установить зависимости
pip install websockets

# 2. Настроить API ключ
export XAI_API_KEY="your-api-key"

# 3. Запустить пилот
python auto_call_pilot.py

# 4. Проанализировать результаты
python pilot_results.py
```

## Метрики для сравнения

| Метрика | baresip | x.ai | Цель |
|---------|---------|------|------|
| Конверсия (ДА) | ?% | ?% | +20% |
| Средняя длительность | ? сек | ? сек | < 60 сек |
| Стоимость за звонок | $0 | $0.05 | <$0.10 |
| Качество диалога | Низкое | Высокое | Субъективно |

## Следующие шаги после пилота

1. **Если x.ai лучше:**
   - Интегрировать Function calling (Bitrix24, Telegram)
   - Добавить fallback на baresip при ошибках
   - Настроить кастомные голоса

2. **Если baresip лучше:**
   - Оставить текущую архитектуру
   - Улучшить STT (Whisper large)
   - Добавить адаптивные скрипты

3. **Гибрид:**
   - x.ai для сложных звонков
   - baresip для простых подтверждений
