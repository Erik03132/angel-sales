import os
import json
import logging
from typing import Dict, Any, Optional
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Инициализация Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logger.warning("GEMINI_API_KEY не найден в окружении! Транскрипция работать не будет.")

# Системный промпт для анализа звонков (Строго для Азовского Инкубатора)
SYSTEM_PROMPT = """
Ты — старший аудитор отдела контроля качества «Азовского Инкубатора». 
Твоя задача — прослушать запись телефонного разговора между менеджером инкубатора и клиентом, а затем выгрузить структурированный анализ в формате JSON.

Ключевые бизнес-правила Азовского Инкубатора:
- Адрес: Крым, Джанкойский район, Азовское, Железнодорожная 42. В Москве точек нет.
- Доставка: Только по основной трассе! Заезды в сёла строго запрещены.
- Минимальный заказ: Бройлеры от 50 шт, Утки от 20 шт, Индюки от 10 шт.
- Цены: Кобб-500 = 90₽, Росс-308 = 85₽ (цены до 100 шт).
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
    """Анализатор аудио-звонков на базе Gemini 2.5 Flash"""
    
    def __init__(self, model_name: str = "gemini-2.5-flash"):
        self.model_name = model_name
        self._is_ready = bool(GEMINI_API_KEY)
        self.model = None
        if self._is_ready:
            self.model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=SYSTEM_PROMPT,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,  # Низкая температура для строго JSON
                    response_mime_type="application/json",
                )
            )

    def analyze_audio_file(self, file_path: str) -> Dict[str, Any]:
        """
        Загружает аудио файл в Google API и анализирует его
        """
        if not self._is_ready:
            return {"error": "Gemini API Key missing"}
            
        if not os.path.exists(file_path):
            return {"error": f"File not found: {file_path}"}
            
        logger.info(f"Начинаю загрузку аудиофайла: {os.path.basename(file_path)}")
        
        try:
            # Загружаем файл в инфраструктуру Google (для экономии токенов и работы с аудио)
            audio_file = genai.upload_file(path=file_path)
            logger.info(f"Файл загружен. URI: {audio_file.uri}")
            
            prompt = "Пожалуйста, проанализируй эту запись звонка и верни JSON согласно системным инструкциям."
            
            logger.info("Отправляю запрос к Gemini...")
            response = self.model.generate_content(
                [prompt, audio_file],
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                }
            )
            
            # Парсим JSON ответ
            result_json = response.text.strip()
            
            # Удаляем мусорные теги если Gemini всё-таки их вернула
            if result_json.startswith('```json'):
                result_json = result_json[7:]
            if result_json.startswith('```'):
                result_json = result_json[3:]
            if result_json.endswith('```'):
                result_json = result_json[:-3]
                
            data = json.loads(result_json.strip())
            
            # Очищаем ресурс в облаке
            try:
                genai.delete_file(audio_file.name)
                logger.info("Временный аудиофайл удалён из облака Google.")
            except Exception as cleanup_err:
                logger.warning(f"Не удалось удалить файл из облака: {cleanup_err}")
                
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}\nТекст: {response.text}")
            return {"error": "Invalid JSON format returned by LLM"}
        except Exception as e:
            logger.error(f"Критическая ошибка анализа: {e}")
            return {"error": str(e)}

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
    # Переинициализация для теста (т.к. .env грузился после импорта)
    if os.getenv("GEMINI_API_KEY"):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        
    print("🎙 Тестируем инициализацию CallAnalyzer...")
    analyzer = CallAnalyzer()
    print("✅ Анализатор инициализирован.")
    print("Транскрипция будет использовать Audio Understanding из Gemini 1.5 Pro.")
