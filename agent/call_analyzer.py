import json
import logging
import os
from typing import Any, Dict

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
PROXY_URL = os.getenv("TELEGRAM_PROXY") or "socks5h://Q3NeJXTY:dsBaWh2L@172.120.21.141:64469"

ANALYZE_MODELS = [
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "openai/gpt-oss-20b:free",
]

SYSTEM_PROMPT = """
Ты — старший аудитор отдела контроля качества «Азовского Инкубатора». 
Твоя задача — прослушать запись телефонного разговора между менеджером инкубатора и клиентом, а затем выгрузить структурированный анализ в формате JSON.

Ключевые бизнес-правила Азовского Инкубатора:
- Адрес: Крым, Джанкойский район, Азовское, Железнодорожная 42. В Москве точек нет.
- Доставка: Только по основной трассе! Заезды в сёла строго запрещены.
- Минимальный заказ: Бройлеры от 50 шт, Утки от 20 шт, Индюки от 10 шт.
- Цены: Кобб-500 = 90р, Росс-308 = 85р (цены до 100 шт).
- Утка в этом году отгружается БЕЗ ветсправок, на бройлеров ветсправки есть.

Твоя задача:
1. Кратко пересказать суть звонка (1-2 предложения).
2. Выявить запрошенные пароды и количества.
3. Оценить менеджера по 10-балльной шкале (вежливость, знание продукта, попытка кросс-сейла: предложил ли корм, аптечку?).
4. Выявить возражения клиента (если были) и как менеджер их отработал.
5. Финализировать статус: Сделка успешна (договорились), Отказ, или Ожидание.

Тебе нужно строго вернуть JSON-объект следующего формата:
{
  "summary": "Краткое описание звонка",
  "client_needs": {
    "breed": "Кобб-500",
    "quantity": 100,
    "city_or_delivery": "Симферополь"
  },
  "manager_score": 8,
  "manager_mistakes": ["Не предложил корм", "Не назвал минимальный порог"],
  "cross_sell_attempted": false,
  "client_objections": ["Дорого по сравнению с конкурентом X"],
  "deal_status": "Ожидание"
}

Отвечай ТОЛЬКО сырым JSON без маркдаун разметки (без ```json).
"""


class CallAnalyzer:
    """Анализатор аудио-звонков: Whisper (ASR) + OpenRouter free cascade (анализ)"""
    
    def __init__(self):
        self._is_ready = bool(OPENROUTER_KEY)
        self._whisper = None

    def _get_whisper(self):
        if self._whisper is None:
            try:
                from faster_whisper import WhisperModel
                self._whisper = WhisperModel("tiny", device="cpu", compute_type="int8")
            except ImportError:
                logger.error("faster-whisper не установлен")
                return None
        return self._whisper

    def analyze_audio_file(self, file_path: str) -> Dict[str, Any]:
        if not self._is_ready:
            return {"error": "OPENROUTER_API_KEY not set"}
        if not os.path.exists(file_path):
            return {"error": f"File not found: {file_path}"}

        # === Фаза 1: Whisper ASR ===
        logger.info(f"Транскрибирую: {os.path.basename(file_path)}")
        whisper = self._get_whisper()
        if whisper is None:
            return {"error": "Whisper model not loaded"}

        try:
            segments, info = whisper.transcribe(file_path, language="ru")
            transcript = "\n".join(f"[{seg.start:.1f}s] {seg.text.strip()}" for seg in segments)
            if not transcript.strip():
                logger.warning("Whisper: пустой транскрипт")
                return {"error": "Empty transcript"}
            logger.info(f"Whisper OK: {info.duration:.0f}s")
        except Exception as e:
            logger.error(f"Whisper error: {e}")
            return {"error": f"Whisper failed: {e}"}

        # === Фаза 2: OpenRouter free анализ ===
        import requests
        proxies = {"https": PROXY_URL, "http": PROXY_URL}
        for model in ANALYZE_MODELS:
            try:
                resp = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT.strip()},
                            {"role": "user", "content": transcript},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 1024,
                    },
                    proxies=proxies,
                    timeout=60,
                )
                if resp.status_code == 200:
                    raw = resp.json()["choices"][0]["message"]["content"].strip()
                    if "```json" in raw:
                        raw = raw.split("```json")[1].split("```")[0].strip()
                    elif "```" in raw:
                        raw = raw.split("```")[1].split("```")[0].strip()
                    result = json.loads(raw)
                    result["_transcript"] = transcript
                    logger.info(f"Analyzed via {model}")
                    return result
                else:
                    logger.warning(f"{model}: {resp.status_code}")
            except Exception as e:
                logger.warning(f"{model}: {e}")

        return {"error": "All LLMs failed", "transcript": transcript}

    def is_ready(self) -> bool:
        return self._is_ready
