import asyncio
import csv
import os
import re
import time

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.types import BotCommand
from angelochka_core import get_answer
from client_memory import memory as client_memory
from dotenv import load_dotenv
from persistent_history import chat_db

# voice_engine отключён (требует torch — не установлен)

# 1. Загрузка окружения
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AGENT_ENV = os.path.join(BASE_DIR, ".env")
load_dotenv(override=True)
if not os.getenv("ANGELOCHKA_BOT_TOKEN"):
    load_dotenv(_AGENT_ENV, override=True)
# Гарантируем загрузку всех переменных из .env проекта
load_dotenv(_AGENT_ENV, override=False)

TELEGRAM_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ ANGELOCHKA_BOT_TOKEN не найден в .env!")

# 2. Логи
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
HISTORY_LOG_PATH = os.path.join(LOG_DIR, "history.md")

# Буфер pending_posts (для morning_post.py)
PENDING_DIR = os.path.join(BASE_DIR, "data", "pending_posts")

# 3. Бот (через SOCKS5 — прямой доступ к TG заблокирован)
PROXY_URL = os.getenv("TELEGRAM_PROXY", "")

def _make_session(proxy_url: str):
    """Создаём сессию с SOCKS5 прокси (прямое соединение не работает из РФ)."""
    if proxy_url and (proxy_url.startswith("socks5://") or proxy_url.startswith("socks5h://")):
        try:
            proxy_print = proxy_url.split("@")[-1] if "@" in proxy_url else proxy_url
            session = AiohttpSession(proxy=proxy_url, timeout=120.0)
            print(f"  🔌 Сессия через SOCKS5 ({proxy_print}), timeout=120")
            return session
        except Exception as e:
            print(f"  ⚠️ SOCKS5 не подключился ({e}), падаю на прямое соединение")

    print("  ✅ Прямое соединение, timeout=120")
    return AiohttpSession(timeout=120.0)


# Bot и Dispatcher создаются позже внутри main()
bot: "Bot | None" = None
dp = Dispatcher()

user_histories = {}

_admin_id_raw = os.getenv("ADMIN_TELEGRAM_ID", "").strip()
if not _admin_id_raw:
    raise ValueError(
        "❌ ADMIN_TELEGRAM_ID не задан в .env! "
        "Добавь: ADMIN_TELEGRAM_ID=176203333"
    )
try:
    ADMIN_ID = int(_admin_id_raw)
except ValueError:
    raise ValueError("ADMIN_TELEGRAM_ID пустой или не является integer!")

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
            f"📈 /report — полный отчёт\n"
            f"📅 /daily — бизнес-отчёт дня\n"
            f"🎯 /avito_audit — аудит Авито\n"
            f"🔄 /restart — перезапуск бота"
        )
    else:
        await message.answer("Привет! Я Анжела 🐣 Помогу с выбором птицы, ценами и доставкой. Чем могу помочь?")


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


@dp.message(Command("daily"))
async def cmd_daily(message: types.Message):
    """Команда /daily — генерация и отправка бизнес-отчёта и сводки."""
    if not is_admin(message.from_user.id) and message.from_user.id != 444248782: # Разрешаем и Игорю, и Андрею
        return

    await message.answer("📊 Формирую ежедневный бизнес-отчёт из CRM...\n⏳ Это займёт около 30-40 секунд (работает ИИ).")

    try:
        import sys
        sys.path.insert(0, AGENT_DIR)
        from daily_report import run_daily_report
        
        # Запускаем генерацию в отдельном потоке
        report_text = await asyncio.to_thread(run_daily_report)
        
        if report_text:
            if len(report_text) <= 4000:
                await message.answer(report_text)
            else:
                parts = [report_text[i:i+4000] for i in range(0, len(report_text), 4000)]
                for part in parts[:3]:
                    await message.answer(part)
        else:
            await message.answer("⚠️ Не удалось сгенерировать отчёт.")
    except Exception as e:
        await message.answer(f"❌ Ошибка генерации отчёта: {e}")

    # === Блок 2: Сводка по звонкам из транскриптов ===
    try:
        import sys
        sys.path.insert(0, AGENT_DIR)
        from call_daily_summary import get_call_summary
        call_text = await asyncio.to_thread(get_call_summary)
        if call_text:
            await message.answer(call_text, parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"⚠️ Сводка по звонкам: {e}")

@dp.message(Command("report"))
async def cmd_report(message: types.Message):
    """Команда /report — полный разведывательный отчёт Битрикс24 (только для Игоря)."""
    if not is_admin(message.from_user.id):
        return

    await message.answer("🕵️ Собираю полный отчёт: сделки, звонки, задачи, рабочее время...\n⏳ 10-15 сек.")

    try:
        import sys
        sys.path.insert(0, AGENT_DIR)
        from bitrix_intelligence import digest_to_markdown, run_intelligence

        digest = await asyncio.to_thread(run_intelligence)

        if digest:
            md = digest_to_markdown(digest)
            # Telegram лимит 4096 — разбиваем
            if len(md) <= 4000:
                await message.answer(md)
            else:
                parts = [md[i:i+4000] for i in range(0, len(md), 4000)]
                for part in parts[:3]:
                    await message.answer(part)
        else:
            await message.answer("⚠️ Разведка не удалась. Проверь подключение к Битрикс24.")
    except Exception as e:
        await message.answer(f"❌ Ошибка отчёта: {e}")


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
# 📞 AUTO-CALL — Загрузка CSV → обзвон → отчёт в TG
# ============================================================


# Буфер для хранения пути к загруженному CSV между handler и callback
_autocall_csv_path: str | None = None
_autocall_contacts: list = []


@dp.message(F.document)
async def handle_csv_document(message: types.Message):
    """Принимает CSV файл с контактами для обзвона."""
    global _autocall_csv_path, _autocall_contacts

    if not is_admin(message.from_user.id):
        return

    doc = message.document
    if not (doc.file_name.endswith(".csv") or doc.file_name.endswith(".txt")):
        await message.answer("❌ Пришли CSV или TXT файл ( name,phone,product,delivery_location )")
        return

    await message.answer("📋 Скачиваю CSV...")

    try:
        import io
        file_io = await bot.download(doc.file_id)
        if hasattr(file_io, "read"):
            file_bytes = file_io.read()
        else:
            file_bytes = file_io
        text = file_bytes.decode("utf-8")
    except Exception as e:
        await message.answer(f"❌ Ошибка скачивания: {e}")
        return

    # Извлекаем телефоны (поддержка: CSV с колонкой phone, или просто список номеров)
    phones = []
    try:
        # Пробуем как CSV с заголовком
        first_line = text.strip().split("\n")[0].lower()
        if "phone" in first_line or "," in first_line:
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                phone = row.get("phone", "") or row.get("Phone", "") or list(row.values())[0]
                phone = str(phone).strip()
                if phone and re.search(r'\d{10,}', phone):
                    phones.append(phone)
        # Иначе — простой список номеров (один на строку)
        if not phones:
            for line in text.strip().split("\n"):
                line = line.strip().strip(",").strip()
                if line and re.search(r'\d{10,}', line):
                    # Берём только цифры/+/-/()
                    phone_match = re.search(r'[+\d][\d\s\-\(\)]{9,}', line)
                    if phone_match:
                        phones.append(phone_match.group().strip())
    except Exception as e:
        await message.answer(f"❌ Ошибка парсинга файла: {e}")
        return

    if not phones:
        await message.answer("❌ В файле не найдено телефонов")
        return

    _autocall_contacts = phones

    # Показываем список и кнопки подтверждения
    lines = [f"{i}. {p}" for i, p in enumerate(phones, 1)]
    preview = "\n".join(lines[:20])
    if len(phones) > 20:
        preview += f"\n... и ещё {len(phones) - 20}"

    await message.answer(
        f"📞 Обзвон: {len(phones)} номеров\n\n"
        f"{preview}\n\n"
        f"⚠️ Будет использован уже загруженный WAV на VPS\n\n"
        f"Начать обзвон?",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📞 Позвонить всем", callback_data="autocall_start")],
            [types.InlineKeyboardButton(text="❌ Отмена", callback_data="autocall_cancel")],
        ])
    )


@dp.callback_query(F.data == "autocall_start")
async def autocall_start(callback: types.CallbackQuery):
    """Запускает обзвон после подтверждения. Использует уже загруженный WAV на VPS."""
    global _autocall_csv_path, _autocall_contacts

    if not is_admin(callback.from_user.id):
        return

    if not _autocall_contacts:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("❌ Список номеров пуст. Загрузите файл заново.")
        return

    phones = _autocall_contacts
    count = len(phones)

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"📞 Запускаю обзвон {count} номеров...\n⏳ ~35 сек на номер, отчёт после всех звонков.")

    try:
        import sys
        sys.path.insert(0, AGENT_DIR)

        # КРИТИЧНО: убираем SOCKS-прокси перед звонком в Mango (RU API)
        for _p in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY",
                   "https_proxy", "http_proxy", "all_proxy"):
            os.environ.pop(_p, None)

        from mango_autocall import make_call

        # Запоминаем время старта для фильтрации результатов из call_results.csv
        start_ts = time.time()

        # Звоним последовательно
        call_data = []
        for i, phone in enumerate(phones, 1):
            # Нормализуем телефон: +79... или 79... → +7...
            phone_clean = re.sub(r'[\s\-\(\)]', '', phone)
            if not phone_clean.startswith("+"):
                if phone_clean.startswith("8"):
                    phone_clean = "+7" + phone_clean[1:]
                elif phone_clean.startswith("7"):
                    phone_clean = "+" + phone_clean
                else:
                    phone_clean = "+" + phone_clean

            try:
                result = await asyncio.to_thread(make_call, phone_clean)
                api_ok = result.get("result") == 1000
                call_data.append({
                    "phone": phone_clean,
                    "command_id": result.get("command_id"),
                    "status": "called" if api_ok else "call_failed",
                })
            except Exception as e:
                call_data.append({"phone": phone_clean, "status": f"error: {e}"})

            # Пауза между звонками
            if i < count:
                await asyncio.sleep(35)

        # Поллим call_results.csv с VPS пока не появятся результаты (макс 5 мин)
        dtmf_results = {}
        poll_deadline = time.time() + 300  # 5 минут макс (STT может быть медленным)
        expected_phones = {re.sub(r'\D', '', c["phone"])[-10:] for c in call_data if c.get("status") == "called"}
        poll_count = 0
        print(f"📊 Ожидаем результаты для {len(expected_phones)} номеров: {expected_phones}")

        # SSH ключ для доступа к VPS
        ssh_key = "/Users/igorvasin/freelance-2026/.ssh_agent_key"

        while time.time() < poll_deadline:
            await asyncio.sleep(20)
            poll_count += 1

            try:
                import subprocess
                # Читаем ТОЛЬКО основной CSV (не cat нескольких файлов — дубли ломают парсинг)
                ssh_cmd = [
                    "ssh", "-i", ssh_key,
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "ConnectTimeout=10",
                    "root@72.56.38.19",
                    "cat /opt/data/mango/call_results.csv 2>/dev/null || echo ''",
                ]
                result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=20)
                csv_text = result.stdout
                if not csv_text.strip():
                    print(f"📊 Poll #{poll_count}: CSV пуст")
                    continue

                from datetime import datetime, timezone
                from io import StringIO
                reader = csv.DictReader(StringIO(csv_text))
                fresh = {}
                for row in reader:
                    ts_str = row.get("timestamp", "")
                    try:
                        # ВАЖНО: VPS в UTC, datetime.now() на VPS пишет UTC
                        # Парсим как UTC, а start_ts (time.time()) тоже UTC epoch
                        naive_dt = datetime.fromisoformat(ts_str)
                        utc_dt = naive_dt.replace(tzinfo=timezone.utc)
                        ts = utc_dt.timestamp()
                        if ts < start_ts:
                            continue
                    except (ValueError, TypeError):
                        continue
                    phone_raw = row.get("phone", "") or row.get("to_number", "")
                    phone_key = re.sub(r'[\+\s\-\(\)]', '', phone_raw)
                    action = row.get("action", "unknown")
                    if phone_key and phone_key != "неизвестен" and phone_key != "unknown":
                        # Не перезатираем definitive результат (confirmed/cancelled)
                        # на unclear/unknown — приоритет у чёткого ответа
                        existing = fresh.get(phone_key)
                        if existing in ("confirmed", "cancelled") and action not in ("confirmed", "cancelled"):
                            continue  # не перезатираем
                        fresh[phone_key] = action

                print(f"📊 Poll #{poll_count}: найдено {len(fresh)} свежих результатов: {fresh}")

                if fresh:
                    dtmf_results = fresh
                    # Проверяем, все ли ожидаемые номера получили ОПРЕДЕЛЁННЫЙ ответ
                    # (unclear/unknown — НЕ считается финальным, ждём DTMF/STT)
                    definitive = 0
                    for ep in expected_phones:
                        for k, action in fresh.items():
                            if k.endswith(ep) or ep.endswith(k[-10:]):
                                if action in ("confirmed", "cancelled"):
                                    definitive += 1
                                break
                    if definitive >= len(expected_phones):
                        print(f"📊 Все {definitive}/{len(expected_phones)} номеров получили чёткий ответ — стоп")
                        break
                    # Есть результаты, но не все определённые — ждём ещё
                    print(f"📊 Определённых: {definitive}/{len(expected_phones)} — ждём DTMF/STT...")
            except Exception as e:
                print(f"⚠️ Poll VPS results error (#{poll_count}): {e}")

        if not dtmf_results:
            print(f"⚠️ Таймаут поллинга: за {poll_count} попыток результаты не найдены")

        # Формируем отчёт
        confirmed = []
        refused = []
        unclear = []
        no_result = []

        for c in call_data:
            phone = c["phone"]
            status = c.get("status", "?")
            # phone_key — последние 10 цифр (универсальное сравнение)
            phone_digits = re.sub(r'\D', '', phone)
            phone_key = phone_digits[-10:] if len(phone_digits) >= 10 else phone_digits

            # Ищем по последним 10 цифрам
            action = None
            for k, v in dtmf_results.items():
                k_digits = re.sub(r'\D', '', k)
                if k_digits.endswith(phone_key) or phone_key.endswith(k_digits[-10:]):
                    action = v
                    break

            if status == "called":
                if action == "confirmed":
                    confirmed.append(phone)
                elif action == "cancelled":
                    refused.append(phone)
                elif action in ("unclear", "unknown"):
                    unclear.append(phone)
                else:
                    no_result.append(phone)
            else:
                no_result.append(f"{phone} ({status})")

        lines = [f"📊 Отчёт по обзвону ({count} номеров)\n"]

        if confirmed:
            lines.append(f"✅ Подтвердили ({len(confirmed)}):")
            for p in confirmed:
                lines.append(f"  ✅ {p}")
            lines.append("")

        if refused:
            lines.append(f"❌ Отказали ({len(refused)}):")
            for p in refused:
                lines.append(f"  ❌ {p}")
            lines.append("")

        if unclear:
            lines.append(f"❓ Неразборчиво ({len(unclear)}):")
            for p in unclear:
                lines.append(f"  ❓ {p}")
            lines.append("")

        if no_result:
            lines.append(f"⚠️ Нет ответа ({len(no_result)}):")
            for p in no_result:
                lines.append(f"  ⚠️ {p}")
            lines.append("")

        lines.append(f"📈 Итого: {len(confirmed)} ✅ | {len(refused)} ❌ | {len(unclear)} ❓ | {len(no_result)} ⚠️")

        report_text = "\n".join(lines)
        # TG лимит 4096
        if len(report_text) > 4000:
            report_text = report_text[:3997] + "..."
        await callback.message.answer(report_text)

    except Exception as e:
        import traceback
        traceback.print_exc()
        await callback.message.answer(f"❌ Ошибка обзвона: {e}")

    finally:
        _autocall_csv_path = None
        _autocall_contacts = []


@dp.callback_query(F.data == "autocall_cancel")
async def autocall_cancel(callback: types.CallbackQuery):
    """Отменяет обзвон."""
    global _autocall_csv_path, _autocall_contacts

    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("❌ Обзвон отменён.")

    _autocall_csv_path = None
    _autocall_contacts = []


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

        response = await asyncio.to_thread(get_answer, enriched_text, history, sender_id=str(user_id), sender_name=user_name, channel="tg")

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

        # === ГОЛОСОВОЙ ОТВЕТ ОТКЛЮЧЁН (ускорение) ===
        await message.answer(response)

    except Exception as e:
        print(f"ERROR in chat_handler: {e}")
        import traceback
        traceback.print_exc()
        await message.answer("Прости, у меня мини-сбой... Повтори вопрос через пару секунд! 🐣")


# ============================================================
# 🔘 INLINE KЕЙБОРДЫ (Одобрение контента)
# ============================================================
@dp.callback_query(F.data == "approve_draft")
async def approve_draft_callback(callback: types.CallbackQuery):
    print(f"🎯 Callback 'approve_draft' от {callback.from_user.id}")
    if not is_admin(callback.from_user.id):
        print(f"⚠️ Отказ: {callback.from_user.id} не админ")
        return await callback.answer("У вас нет прав!", show_alert=True)
        
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply("🚀 Принято, шеф! Раскидываю статью по папкам на Диске...")
    
    try:
        import json
        import sys
        sys.path.insert(0, AGENT_DIR)
        from bitrix_disk_manager import BitrixDiskManager
        
        draft_path = os.path.join(BASE_DIR, 'data', 'content_drafts', 'last_draft.json')
        if os.path.exists(draft_path):
            with open(draft_path, 'r', encoding='utf-8') as f:
                draft = json.load(f)
            
            def upload_sync():
                disk = BitrixDiskManager()
                root_id = disk.get_or_create_root_folder()
                article_root = disk.create_subfolder(root_id, draft['folder_name'])
                mapping = {"zen": "01_DZEN", "vk": "02_VK", "ok": "03_OK", "max": "04_MAX", "industry": "05_ARCHIVE"}
                for k, fbase in mapping.items():
                    if k in draft['content']:
                        sub_id = disk.create_subfolder(article_root, fbase)
                        ftext = str(draft['content'][k]) if not isinstance(draft['content'][k], dict) else json.dumps(draft['content'][k], ensure_ascii=False)
                        disk.upload_file(sub_id, f"{k}_version.md", ftext)
            
            await asyncio.to_thread(upload_sync)
            await callback.message.reply(f"✅ Успешно! Все форматы статьи «{draft['topic']}» сохранены на твоем Диске на сервере Битрикс24.")
        else:
            await callback.message.reply("⚠️ Ой, черновик в памяти не найден.")
    except Exception as e:
        await callback.message.reply(f"❌ Техническая ошибка при сохранении: {e}")

@dp.callback_query(F.data == "reject_draft")
async def reject_draft_callback(callback: types.CallbackQuery):
    print(f"🎯 Callback 'reject_draft' от {callback.from_user.id}")
    if not is_admin(callback.from_user.id):
        return await callback.answer("У вас нет прав!", show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply("📝 Поняла, убираем в стол! Можешь написать мне свои исправления в чат.")


# ============================================================
# 📡 CONTENT HUB — Кнопки утреннего поста
# ============================================================

@dp.callback_query(F.data.startswith("content_approve:"))
async def content_approve_handler(callback: types.CallbackQuery):
    """✅ Отправить — веерная публикация на все площадки."""
    if not is_admin(callback.from_user.id):
        return await callback.answer("У вас нет прав!", show_alert=True)

    post_id = callback.data.split(":", 1)[1]
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("🚀 Отправляю на все площадки...")

    try:
        import sys
        sys.path.insert(0, AGENT_DIR)
        from fan_publish import fan_publish

        results = await asyncio.to_thread(fan_publish, post_id)

        if results:
            lines = []
            for platform, ok in results.items():
                emoji = "✅" if ok else "❌"
                lines.append(f"  {emoji} {platform.upper()}")
            report = "\n".join(lines)
            ok_count = sum(1 for v in results.values() if v)
            total = len(results)
            await callback.message.reply(
                f"📡 Публикация завершена ({ok_count}/{total}):\n\n{report}"
            )
        else:
            await callback.message.reply("❌ Пост не найден в буфере.")
    except Exception as e:
        await callback.message.reply(f"❌ Ошибка публикации: {e}")


@dp.callback_query(F.data.startswith("content_more:"))
async def content_more_handler(callback: types.CallbackQuery):
    """🔄 Ещё — генерация нового поста на замену."""
    if not is_admin(callback.from_user.id):
        return await callback.answer("У вас нет прав!", show_alert=True)

    post_id = callback.data.split(":", 1)[1]
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("🔄 Генерирую новый пост...")
    await callback.message.reply("🔄 Генерирую замену, подожди ~30 сек...")

    try:
        import sys
        sys.path.insert(0, AGENT_DIR)
        from fan_publish import load_pending
        from morning_post import morning_generate

        # Определяем бренд из старого поста
        old = load_pending(post_id)
        brand_key = old["brand"] if old else "podvorye"

        new_post_id = await asyncio.to_thread(morning_generate, brand_key)
        if new_post_id:
            await callback.message.reply("✅ Новый пост готов! Смотри выше ☝️")
        else:
            await callback.message.reply("❌ Не удалось сгенерировать. Попробуй позже.")
    except Exception as e:
        await callback.message.reply(f"❌ Ошибка генерации: {e}")


@dp.callback_query(F.data.startswith("content_two:"))
async def content_two_handler(callback: types.CallbackQuery):
    """📋 Два поста — добавить второй пост."""
    if not is_admin(callback.from_user.id):
        return await callback.answer("У вас нет прав!", show_alert=True)

    post_id = callback.data.split(":", 1)[1]
    # НЕ убираем кнопки у первого поста — он остаётся для публикации
    await callback.answer("📋 Генерирую второй пост...")
    await callback.message.reply("📋 Генерирую дополнительный пост, подожди ~30 сек...")

    try:
        import sys
        sys.path.insert(0, AGENT_DIR)
        from fan_publish import load_pending
        from morning_post import morning_generate

        old = load_pending(post_id)
        brand_key = old["brand"] if old else "podvorye"

        new_post_id = await asyncio.to_thread(morning_generate, brand_key)
        if new_post_id:
            await callback.message.reply("✅ Второй пост готов! Смотри выше ☝️")
        else:
            await callback.message.reply("❌ Не удалось сгенерировать второй пост.")
    except Exception as e:
        await callback.message.reply(f"❌ Ошибка: {e}")


@dp.callback_query(F.data.startswith("content_only:"))
async def content_only_handler(callback: types.CallbackQuery):
    """⚙️ Только одна площадка — выборочная публикация."""
    if not is_admin(callback.from_user.id):
        return await callback.answer("У вас нет прав!", show_alert=True)

    parts = callback.data.split(":")
    # content_only:dzen:post_id
    platform = parts[1]
    post_id = parts[2]

    await callback.answer(f"📡 Отправляю на {platform.upper()}...")

    try:
        import sys
        sys.path.insert(0, AGENT_DIR)
        from fan_publish import fan_publish

        results = await asyncio.to_thread(fan_publish, post_id, [platform])

        if results.get(platform):
            await callback.message.reply(f"✅ Опубликовано на {platform.upper()}")
        else:
            await callback.message.reply(f"❌ Ошибка публикации на {platform.upper()}")
    except Exception as e:
        await callback.message.reply(f"❌ Ошибка: {e}")


@dp.callback_query(F.data.startswith("content_delete:"))
async def content_delete_handler(callback: types.CallbackQuery):
    """🗑 Удалить превью — очистка TG ленты."""
    if not is_admin(callback.from_user.id):
        return await callback.answer("У вас нет прав!", show_alert=True)

    post_id = callback.data.split(":")[1]

    try:
        # Удаляем сообщение с превью
        await callback.message.delete()
        await callback.answer("🗑 Превью удалено", show_alert=False)
        
        # Также удаляем из буфера (опционально)
        pending_file = os.path.join(PENDING_DIR, f"{post_id}.json")
        if os.path.exists(pending_file):
            os.unlink(pending_file)
            print(f"🗑 Удалён из буфера: {post_id}")
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

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
            print("🧹 Убрана stale lock-файл от мёртвого процесса")
            os.remove(LOCK_FILE)
        except PermissionError:
            # Процесс жив, но чужой — не трогаем
            print("❌ Процесс жив, но недоступен. Отказ в запуске.")
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
    global bot
    # === Инициализируем бота ЗДЕСЬ — внутри event loop ===
    bot = Bot(token=TELEGRAM_TOKEN, session=_make_session(PROXY_URL))

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
        BotCommand(command="report",      description="📈 Полный отчёт"),
        BotCommand(command="daily",       description="📅 Бизнес-отчёт дня"),
        BotCommand(command="avito_audit", description="🎯 Аудит Авито"),
        BotCommand(command="restart",     description="🔄 Перезапуск"),
        BotCommand(command="call",        description="📞 Обзвон (пришли CSV)"),
    ]

    # Skip menu registration as it hangs
    print("   ⏩ Пропускаю регистрацию меню")

    # Retry loop с backoff при ConflictError
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            print(f"   ⏳ Удаление вебхука (попытка {attempt})...")
            await bot.delete_webhook(drop_pending_updates=True)
            print(f"   🚀 Запускаю polling (попытка {attempt}/{max_retries})...\n")
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
    """Graceful shutdown: останавливаем polling, закрываем сессию, чистим lock."""
    print("\n🛑 Получен сигнал завершения. Останавливаю бота...")
    _release_lock()
    await dp.stop_polling()
    if bot:
        await bot.session.close()
        print("🔒 Сессия закрыта")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        _release_lock()
