"""
VK Bot для сообщества «ВезёмЦыплят» (club238316002)
Анжела отвечает на сообщения клиентов через VK Long Poll API.

Требования:
  - В настройках группы ВК: Сообщения → Включены
  - Long Poll API → Включен, версия 5.199+
  - Типы событий → message_new (галка)
  - .env: VK_VEZEMCYP_TOKEN, VK_VEZEMCYP_GROUP_ID

Запуск: python3 vk_bot.py
PM2:    pm2 start ecosystem.config.js --only angela-vk-bot
"""

import logging
import os
import re
import time
import traceback

import vk_api
from angelochka_core import get_answer
from client_memory import memory as client_memory
from dotenv import load_dotenv
from vk_api.bot_longpoll import VkBotEventType, VkBotLongPoll

# ─── Загрузка окружения ───────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

# Токен и ID группы ВезёмЦыплят
VK_TOKEN = os.getenv("VK_VEZEMCYP_TOKEN")
VK_GROUP_ID = os.getenv("VK_VEZEMCYP_GROUP_ID", "")

if not VK_TOKEN or not VK_GROUP_ID:
    print("❌ VK_VEZEMCYP_TOKEN или VK_VEZEMCYP_GROUP_ID не найдены в .env!")

# Очистка ID группы (должен быть положительным числом для LongPoll)
VK_GROUP_ID_CLEAN = VK_GROUP_ID.lstrip("-") if VK_GROUP_ID else ""

# ─── Логи ─────────────────────────────────────────────────────────
LOG_DIR = os.path.join(AGENT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
VK_LOG_PATH = os.path.join(LOG_DIR, "vk_history.md")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [VK-BOT] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("vk_bot")

# ─── Persistent History (Neon DB) ─────────────────────────────────
_chat_db = None
try:
    from persistent_history import chat_db
    if chat_db._available:
        _chat_db = chat_db
        log.info("✅ Persistent history подключена (Neon)")
    else:
        log.warning("⚠️ Persistent history недоступна, используем in-memory")
except Exception as e:
    log.warning(f"⚠️ Persistent history не загрузилась: {e}")

# In-memory fallback для истории
_sessions = {}
MAX_HISTORY = 20

# ─── Rate Limiting ────────────────────────────────────────────────
_last_reply_time = {}
MIN_REPLY_INTERVAL = 1.0  # секунда между ответами одному юзеру

# ─── Reconnect config ────────────────────────────────────────────
RECONNECT_DELAY = 5       # секунд между реконнектами
MAX_RECONNECT_DELAY = 120  # макс. задержка


def save_to_log(user_id, name, text, direction="IN"):
    """Сохраняет сообщение в файл-лог."""
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(VK_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"**[{ts} | {direction} | VK:{user_id} | {name}]**: {text}\n\n")
    except Exception as e:
        log.error(f"VK Log write failed: {e}")


def load_history(user_id: str) -> list:
    """Загружает историю диалога из Neon DB или in-memory."""
    client_key = f"vk_{user_id}"
    if _chat_db:
        try:
            return _chat_db.load_history(user_id=client_key)
        except Exception as e:
            log.error(f"DB history load error: {e}")
    return _sessions.get(client_key, [])


def save_history(user_id: str, role: str, content: str, user_name: str = ""):
    """Сохраняет сообщение в историю (Neon DB или in-memory)."""
    client_key = f"vk_{user_id}"
    if _chat_db:
        try:
            _chat_db.save_message(
                user_id=client_key,
                role=role,
                content=content,
                user_name=user_name or client_key
            )
            return
        except Exception as e:
            log.error(f"DB history save error: {e}")

    # Fallback: in-memory
    if client_key not in _sessions:
        _sessions[client_key] = []
    _sessions[client_key].append({"role": role, "parts": [content]})
    _sessions[client_key] = _sessions[client_key][-MAX_HISTORY:]


def clean_bot_response(response: str) -> str:
    """Убирает имя бота из начала ответа."""
    response = re.sub(r'^Анжелочка:\s*', '', response, flags=re.IGNORECASE)
    response = re.sub(r'^Анжела:\s*', '', response, flags=re.IGNORECASE)
    response = re.sub(r'^Анжела Заботкина:\s*', '', response, flags=re.IGNORECASE)
    return response.strip()


def split_vk_message(text: str, max_len: int = 4096) -> list:
    """Разбивает длинное сообщение на части (VK лимит 4096 символов)."""
    if len(text) <= max_len:
        return [text]
    parts = []
    while text:
        if len(text) <= max_len:
            parts.append(text)
            break
        # Ищем последний перенос строки или пробел в пределах лимита
        cut = text.rfind('\n', 0, max_len)
        if cut == -1:
            cut = text.rfind(' ', 0, max_len)
        if cut == -1:
            cut = max_len
        parts.append(text[:cut])
        text = text[cut:].lstrip()
    return parts


def handle_message(vk, message):
    """Обрабатывает одно входящее сообщение."""
    user_id = message['from_id']
    text = message.get('text', '').strip()

    if not text:
        return

    # Rate limiting
    now = time.time()
    if user_id in _last_reply_time:
        elapsed = now - _last_reply_time[user_id]
        if elapsed < MIN_REPLY_INTERVAL:
            time.sleep(MIN_REPLY_INTERVAL - elapsed)
    _last_reply_time[user_id] = time.time()

    # Получаем имя пользователя
    try:
        user_info = vk.users.get(user_ids=user_id)[0]
        user_name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
    except Exception:
        user_name = str(user_id)

    log.info(f"📩 {user_name} ({user_id}): {text[:100]}")
    save_to_log(user_id, user_name, text, "IN")

    try:
        # Загружаем историю диалога
        history = load_history(str(user_id))

        # Обогащаем контекстом из памяти
        client_key = f"vk_{user_id}"
        client_context = client_memory.recall(client_key)

        enriched_text = text
        if client_context:
            enriched_text = f"[ПАМЯТЬ О КЛИЕНТЕ:\n{client_context}]\n\nСообщение: {text}"

        # Получаем ответ от Анжелы
        response = get_answer(
            enriched_text,
            history,
            sender_id=str(user_id),
            sender_name=user_name,
            channel="vk"
        )
        response = clean_bot_response(response)

        # Сохраняем историю
        save_history(str(user_id), "user", text, user_name)
        save_history(str(user_id), "model", response, "angelochka")

        # Отправляем ответ (разбиваем если длинный)
        for part in split_vk_message(response):
            vk.messages.send(
                user_id=user_id,
                random_id=int(time.time() * 1000000),  # микросекунды для уникальности
                message=part
            )
            time.sleep(0.35)  # VK rate limit: 3 req/sec

        save_to_log(user_id, user_name, response, "OUT")
        log.info(f"📤 → {user_name}: {response[:80]}...")

        # Обновляем память о клиенте
        client_memory.extract_info_from_text(client_key, text, response)
        if user_name:
            client_memory.remember(client_key, {"name": user_name, "channel": "vk"})

    except Exception as e:
        log.error(f"❌ Ошибка обработки: {e}\n{traceback.format_exc()}")
        try:
            vk.messages.send(
                user_id=user_id,
                random_id=int(time.time() * 1000000),
                message="Простите, у меня небольшая заминка. Повторите, пожалуйста, вопрос! 🐣"
            )
        except Exception:
            pass


def main():
    if not VK_TOKEN:
        print("❌ VK_VEZEMCYP_TOKEN пуст. Бот не запущен.")
        return

    log.info(f"🚀 Запуск VK-бота «ВезёмЦыплят» (group_id={VK_GROUP_ID_CLEAN})...")

    delay = RECONNECT_DELAY

    while True:
        try:
            vk_session = vk_api.VkApi(token=VK_TOKEN)
            vk = vk_session.get_api()
            longpoll = VkBotLongPoll(vk_session, VK_GROUP_ID_CLEAN)

            log.info("✅ Подключение к VK Long Poll установлено. Слушаю сообщения...")
            delay = RECONNECT_DELAY  # Сбрасываем задержку при успешном подключении

            for event in longpoll.listen():
                if event.type == VkBotEventType.MESSAGE_NEW:
                    handle_message(vk, event.obj.message)

        except KeyboardInterrupt:
            log.info("🛑 VK-бот остановлен (Ctrl+C)")
            break

        except Exception as e:
            log.error(f"❌ VK Bot ошибка: {e}")
            log.info(f"🔄 Реконнект через {delay}с...")
            time.sleep(delay)
            delay = min(delay * 2, MAX_RECONNECT_DELAY)  # Exponential backoff


if __name__ == "__main__":
    main()
