import os
import asyncio
import re
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram import F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import BotCommand, BotCommandScopeChat
from dotenv import load_dotenv
from angelochka_core import get_answer
from client_memory import memory as client_memory
from persistent_history import chat_db
from voice_engine import generate_voice, cleanup_voice
from aiogram.types import FSInputFile

# 1. Загрузка окружения
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(override=True)
if not os.getenv("ANGELOCHKA_BOT_TOKEN"):
    load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

TELEGRAM_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ ANGELOCHKA_BOT_TOKEN не найден в .env!")

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

# 2. Логи
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
HISTORY_LOG_PATH = os.path.join(LOG_DIR, "history.md")

# 3. Бот с SOCKS5 прокси (Telegram заблокирован из РФ)
PROXY_URL = os.getenv("TELEGRAM_PROXY", "socks5://172.120.21.141:64469")

session = AiohttpSession(proxy=PROXY_URL, timeout=60)
print(f"✅ Прокси настроен: {PROXY_URL}")

bot = Bot(token=TELEGRAM_TOKEN) # session=session
dp = Dispatcher()

user_histories = {}

ADMIN_ID = 176203333

# Переключатель тишины
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_ONLY_FLAG = os.path.join(AGENT_DIR, "LOG_ONLY")


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def is_silent_mode() -> bool:
    return os.path.exists(LOG_ONLY_FLAG)


# ============================================================
# 🔧 ADMIN COMMANDS — только для хозяина (ID: 176203333)
# ============================================================

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    user_histories[user_id] = []

    if is_admin(user_id):
        mode = "🔇 МОЛЧУН" if is_silent_mode() else "🔊 АКТИВНА"
        await message.answer(
            f"👋 Привет, Игорь!\n\n"
            f"🐣 Анжелочка — Панель управления\n"
            f"Текущий режим: {mode}\n\n"
            f"Твои команды:\n"
            f"📊 /status — статус всей системы\n"
            f"🔇 /silent — Анжела молчит\n"
            f"🔊 /voice — Анжела говорит\n"
            f"📈 /report — отчёт за день\n"
            f"🎯 /avito_audit — аудит Авито\n"
            f"🔄 /restart — перезапуск бота"
        )
    else:
        await message.answer("Привет! Я Анжелочка 🐣 Менеджер Азовского Инкубатора. Чем могу помочь?")


@dp.message(Command("silent"))
async def cmd_silent(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    open(LOG_ONLY_FLAG, 'w').close()
    await message.answer(
        "🔇 Режим МОЛЧУН включён\n\n"
        "Анжела слушает все разговоры в Битриксе,\n"
        "но самостоятельно НЕ отвечает.\n\n"
        "Включить голос: /voice"
    )


@dp.message(Command("voice"))
async def cmd_voice(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    try:
        os.remove(LOG_ONLY_FLAG)
    except FileNotFoundError:
        pass
    await message.answer(
        "🔊 Режим ГОЛОС включён!\n\n"
        "Анжела теперь отвечает всем в Битриксе.\n\n"
        "Заглушить: /silent"
    )


@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    mode = "🔇 МОЛЧУН" if is_silent_mode() else "🔊 АКТИВНА"
    avito_id = os.getenv("AVITO_CLIENT_ID", "")
    gemini = "✅" if os.getenv("GEMINI_API_KEY") else "❌"
    neon = "✅" if os.getenv("NEON_DATABASE_URL") else "❌"
    bitrix = "✅" if os.getenv("BITRIX_WEBHOOK_URL") else "❌"
    avito = "✅" if avito_id else "❌"

    try:
        with open(HISTORY_LOG_PATH, 'r') as f:
            lines = f.readlines()
        msg_count = sum(1 for l in lines if l.startswith("**["))
    except Exception:
        msg_count = 0

    # Статистика облачной истории
    db_stats = await asyncio.to_thread(chat_db.stats)
    if db_stats.get("available"):
        db_line = f"  💾 Облако:  ✅ ({db_stats['total_messages']} сообщ., {db_stats['unique_users']} клиентов)"
    else:
        db_line = "  💾 Облако:  ❌"

    await message.answer(
        f"📊 СТАТУС АНЖЕЛОЧКИ v9.2\n"
        f"{'─'*25}\n"
        f"Режим: {mode}\n\n"
        f"🔌 Подключения:\n"
        f"  Gemini AI: {gemini}\n"
        f"  Neon DB:   {neon}\n"
        f"  Bitrix24:  {bitrix}\n"
        f"  Avito API: {avito}\n"
        f"{db_line}\n\n"
        f"📨 Сообщений в логах: {msg_count}"
    )


@dp.message(Command("report"))
async def cmd_report(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer("📈 Собираю отчёт...")

    try:
        with open(HISTORY_LOG_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        lines = content.strip().split('\n')
        last_lines = '\n'.join(lines[-50:]) if len(lines) > 50 else content
        report = f"📈 ПОСЛЕДНИЕ ДИАЛОГИ:\n\n{last_lines[:3000]}" if last_lines else "Диалогов пока нет."
        await message.answer(report)
    except FileNotFoundError:
        await message.answer("📈 Логи пусты — диалогов не было.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@dp.message(Command("avito_audit"))
async def cmd_avito_audit(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer("🎯 Запускаю аудит Авито...\nЭто займёт 1-2 минуты.")

    try:
        import sys
        sys.path.insert(0, AGENT_DIR)
        from avitolog import Avitolog
        agent = Avitolog()
        report = await asyncio.to_thread(agent.run_full_audit)
        if report and not report.startswith("❌"):
            summary = report[:3500] if len(report) > 3500 else report
            await message.answer(f"✅ Аудит завершён!\n\n{summary}")
        else:
            await message.answer("⚠️ Аудит не удался. Проверь тариф Авито.")
    except Exception as e:
        await message.answer(f"❌ Ошибка аудита: {e}")


@dp.message(Command("restart"))
async def cmd_restart(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("🔄 Перезапускаю бота...")
    await dp.stop_polling()


# ============================================================
# 💬 Обычные сообщения (для всех)
# ============================================================

@dp.message()
async def chat_handler(message: types.Message):
    user_id = message.from_user.id
    user_name = message.from_user.full_name
    text = message.text

    if not text:
        return

    print(f"\n{'='*40}")
    print(f"USER: {user_name} (ID: {user_id})")
    print(f"MSG:  {text}")
    print(f"{'='*40}\n")

    try:
        with open(HISTORY_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"**[{user_name} | {user_id}]**: {text}\n\n")
    except Exception as e:
        print(f"⚠️ History log write failed: {e}")

    if user_id not in user_histories:
        # Загружаем историю из облака при первом обращении
        db_history = await asyncio.to_thread(chat_db.load_history, user_id, 10)
        user_histories[user_id] = db_history if db_history else []
        if db_history:
            print(f"   💾 Загружена облачная история: {len(db_history)} сообщ.")
    history = user_histories[user_id]

    try:
        client_key = f"tg_{user_id}"
        client_context = client_memory.recall(client_key)
        enriched_text = text
        if client_context:
            enriched_text = f"[ПАМЯТЬ О КЛИЕНТЕ:\n{client_context}]\n\nСообщение: {text}"

        response = await asyncio.to_thread(get_answer, enriched_text, history, sender_id=str(user_id), sender_name=user_name)

        client_memory.extract_info_from_text(client_key, text, response)
        if user_name and user_name != str(user_id):
            client_memory.remember(client_key, {"name": user_name})

        response = re.sub(r'^Анжелочка:\s*', '', response, flags=re.IGNORECASE)
        response = re.sub(r'^Анжела:\s*', '', response, flags=re.IGNORECASE)

        if len(response) > 4000:
            response = response[:3997] + "..."

        history.append({"role": "user", "parts": [text]})
        history.append({"role": "model", "parts": [response]})
        user_histories[user_id] = history[-10:]

        # Сохраняем в облако (async-safe)
        asyncio.get_event_loop().run_in_executor(
            None, chat_db.save_message, user_id, "user", text, user_name
        )
        asyncio.get_event_loop().run_in_executor(
            None, chat_db.save_message, user_id, "model", response, None
        )

        try:
            with open(HISTORY_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"**🤖 [Анжела]**: {response}\n\n---\n\n")
        except Exception:
            pass

        print(f"ОТВЕТ: {response[:80]}...")

        if user_id != ADMIN_ID:
            try:
                admin_msg = f"🕵️‍♂️ {user_name}: {text}\n\n🤖 {response}"
                if len(admin_msg) > 4000:
                    admin_msg = admin_msg[:3997] + "..."
                await bot.send_message(ADMIN_ID, admin_msg)
            except Exception:
                pass

        # === ГОЛОСОВОЙ ОТВЕТ ===
        voice_path = await generate_voice(response, str(user_id))
        if voice_path:
            try:
                if len(response) <= 1000:
                    await message.answer_voice(FSInputFile(voice_path), caption=response)
                else:
                    await message.answer_voice(FSInputFile(voice_path))
                    await message.answer(response)
            except Exception as e:
                import traceback
                print(f"⚠️ Voice send error: {e}")
                traceback.print_exc()
                if not is_silent_mode():
                    await message.answer(response)
            finally:
                cleanup_voice(voice_path)
        else:
            await message.answer(response)

    except Exception as e:
        print(f"ERROR in chat_handler: {e}")
        import traceback
        traceback.print_exc()
        await message.answer("Прости, у меня мини-сбой... Повтори вопрос через пару секунд! 🐣")


import signal

LOCK_FILE = os.path.join(LOG_DIR, "bot.lock")


def _acquire_lock():
    """Захватить lock-файл. Если другой экземпляр жив — отказать."""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            # Проверяем жив ли процесс
            os.kill(old_pid, 0)
            # Процесс жив — не запускаемся
            print(f"❌ Другой экземпляр бота уже работает (PID {old_pid})!")
            print(f"   Если это ошибка — удалите {LOCK_FILE}")
            return False
        except (ProcessLookupError, ValueError):
            # Процесс мёртв или PID битый — удаляем stale lock
            print(f"🧹 Убрана stale lock-файл от мёртвого процесса")
            os.remove(LOCK_FILE)
        except PermissionError:
            # Процесс жив, но чужой — не трогаем
            print(f"❌ Процесс жив, но недоступен. Отказ в запуске.")
            return False

    # Записываем свой PID
    with open(LOCK_FILE, 'w') as f:
        f.write(str(os.getpid()))
    return True


def _release_lock():
    """Отпустить lock-файл при завершении."""
    try:
        if os.path.exists(LOCK_FILE):
            with open(LOCK_FILE, 'r') as f:
                lock_pid = int(f.read().strip())
            # Удаляем только СВОЙ lock
            if lock_pid == os.getpid():
                os.remove(LOCK_FILE)
                print("🔓 Lock-файл освобождён")
    except Exception:
        pass


async def main():
    # === Защита от дублей ===
    if not _acquire_lock():
        return

    print("\n🚀 Анжелочка v9.2 [Anti-Conflict + Lock Guard]")
    print(f"   PID:        {os.getpid()}")
    print(f"   Gemini:     {'✅' if os.getenv('GEMINI_API_KEY') else '❌'}")
    print(f"   Neon DB:    {'✅' if os.getenv('NEON_DATABASE_URL') else '❌'}")
    print(f"   Silent Mode: {'🔇 ВКЛ' if is_silent_mode() else '🔊 ВЫКЛ'}")
    print(f"   Admin ID: {ADMIN_ID}")

    # Graceful shutdown по SIGTERM/SIGINT
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(_shutdown()))

    # Регистрируем меню команд — только у тебя в Телеграме
    admin_commands = [
        BotCommand(command="status",      description="📊 Статус системы"),
        BotCommand(command="silent",      description="🔇 Анжела молчит"),
        BotCommand(command="voice",       description="🔊 Анжела говорит"),
        BotCommand(command="report",      description="📈 Отчёт за день"),
        BotCommand(command="avito_audit", description="🎯 Аудит Авито"),
        BotCommand(command="restart",     description="🔄 Перезапуск"),
    ]

    try:
        await bot.set_my_commands(
            admin_commands,
            scope=BotCommandScopeChat(chat_id=ADMIN_ID)
        )
        print(f"   ✅ Меню зарегистрировано для Admin (ID: {ADMIN_ID})")
    except Exception as e:
        print(f"   ⚠️ Меню не зарегистрировано: {e}")

    # Retry loop с backoff при ConflictError
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            print(f"   Запускаю polling (попытка {attempt}/{max_retries})...\n")
            await dp.start_polling(bot, polling_timeout=30)
            break  # Нормальное завершение
        except Exception as e:
            err_str = str(e).lower()
            if "conflict" in err_str or "409" in err_str:
                wait = min(2 ** attempt, 30)
                print(f"⚠️ ConflictError (попытка {attempt}/{max_retries}). "
                      f"Другой экземпляр мешает. Жду {wait}с...")
                await asyncio.sleep(wait)
                continue
            else:
                print(f"❌ Критическая ошибка: {e}")
                break
    else:
        print(f"❌ Не удалось запустить polling после {max_retries} попыток.")

    _release_lock()


async def _shutdown():
    """Graceful shutdown: останавливаем polling и чистим lock."""
    print("\n🛑 Получен сигнал завершения. Останавливаю бота...")
    _release_lock()
    await dp.stop_polling()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        _release_lock()
