#!/usr/bin/env python3
"""
🎙️ VOICE ENGINE — Модуль генерации голосовых ответов Анжелочки.

Использует Silero TTS (v4_ru) - локальную нейросеть с феноменальным уровнем выражения (модель "xenia").
Генерирует wav аудиофайлы для кружочков (Telegram).

Использование:
    from voice_engine import generate_voice
    await generate_voice("Привет! Я Анжелочка.", "output.wav")
"""
import os
import asyncio
import logging
import re
from num2words import num2words
import torch
import soundfile as sf
import urllib.request

logger = logging.getLogger(__name__)

# Папка для временных аудиофайлов
VOICE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_voices")
os.makedirs(VOICE_DIR, exist_ok=True)

# Загружаем Silero TTS (сохраняем локально, чтобы не качать при каждом запуске)
device = torch.device('cpu')
LOCAL_MODEL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'v4_ru.pt')

if not os.path.isfile(LOCAL_MODEL_FILE):
    logger.info("⬇️ Скачиваю модель Silero TTS (~50 MB)...")
    torch.hub.download_url_to_file('https://models.silero.ai/models/tts/ru/v4_ru.pt', LOCAL_MODEL_FILE)

# Инициализируем модель (глобально, чтобы загружалась один раз)
logger.info("🧠 Инициализирую Silero TTS в память...")
model = torch.package.PackageImporter(LOCAL_MODEL_FILE).load_pickle("tts_models", "model")
model.to(device)

def _sync_generate_voice(text: str, file_path: str):
    """Синхронная функция для генерации голоса через PyTorch"""
    sample_rate = 48000
    speaker = 'baya' # baya - другой женский голос, более глубокий и спокойный
    
    # Генерация тензора аудио
    audio = model.apply_tts(
        text=text,
        speaker=speaker,
        sample_rate=sample_rate,
        put_accent=True,
        put_yo=True
    )
    # Сохраняем в OGG OPUS (Telegram требует именно этот формат для кружочков)
    sf.write(file_path, audio.numpy(), sample_rate, format='OGG', subtype='OPUS')


async def generate_voice(text: str, user_id: str) -> str:
    """
    Генерирует голосовое сообщение из текста.
    
    Args:
        text: Текст для озвучки
        user_id: ID пользователя для уникального имени файла
    
    Returns:
        str: Путь к сгенерированному .ogg файлу, либо None при ошибке.
    """
    if not text:
        return None
        
    # 1. Очистка текста от мусора (эмодзи, markdown, спецсимволы)
    clean_text = text
    # Удаляем жирность, курсив
    clean_text = re.sub(r'[*_`]', '', clean_text)
    # Заменяем частотные сокращения для красивого чтения
    clean_text = clean_text.replace("₽", " рублей").replace(" шт.", " штук")
    
    # Конвертируем числа в слова, так как Silero игнорирует цифры
    def convert_num(match):
        return " " + num2words(int(match.group(0)), lang='ru') + " "
    clean_text = re.sub(r'\d+', convert_num, clean_text)
    
    # Удаляем эмодзи (Silero TTS их не любит)
    clean_text = re.sub(r'[^\w\s.,!?А-Яа-яЁёA-Za-z\-:;()]+', '', clean_text)
    
    # Подчищаем двойные пробелы после конвертации
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    if len(clean_text.strip()) < 2:
        return None
        
    # Ограничиваем длину (1000 символов = около 1.5 минут речи)
    if len(clean_text) > 1000:
        clean_text = clean_text[:1000] + "..."
    
    file_path = os.path.join(VOICE_DIR, f"voice_{user_id}.ogg")
    
    try:
        # Silero требует, чтобы не было гигантских текстов без точек, но в основном справляется
        # Запускаем PyTorch-генерацию в фоне, чтобы не блокировать asyncio loop!
        await asyncio.to_thread(_sync_generate_voice, clean_text, file_path)
        logger.info(f"🎙 Сгенерировано голосовое (Silero) для {user_id}")
        return file_path
    except Exception as e:
        logger.error(f"⚠️ Ошибка генерации голоса (Silero): {e}")
        return None

def cleanup_voice(file_path: str):
    """Удаляет временный аудиофайл после отправки."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass

if __name__ == "__main__":
    # Тестовый запуск
    async def test():
        print("🕐 Генерирую тестовый голос Banya...")
        path = await generate_voice("Здравствуйте! Кобб-500 сейчас стоит 90 рублей за штуку. Доставка по Крыму есть! Оформляем?", "test_user")
        print(f"✅ Готово! Файл сохранён: {path}")
    
    asyncio.run(test())
