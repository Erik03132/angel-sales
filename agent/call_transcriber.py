"""
call_transcriber.py — Транскрибатор звонков ВезёмЦыплят
⚠️  ТРЕБУЕТ: HTTPS_PROXY=socks5://... в .env (US прокси обязателен для Gemini из РФ)
=========================================================
Логика:
  1. Берёт звонки из voximplant.statistic.get за ВЧЕРА (или N дней)
  2. Фильтрует: только отвеченные (>MIN_DURATION сек), с RECORD_FILE_ID
  3. Пропускает уже обработанные (кэш processed_calls.json)
  4. Скачивает MP3 из Bitrix через disk.file.get → DOWNLOAD_URL
  5. Отправляет в Gemini Flash (аудио) — получает транскрипт + саммари
  6. Сохраняет в data/transcripts/YYYY-MM-DD/call_{ID}.json
  7. Обновляет COMMENTS звонка в CRM (опционально)

Запуск:
  python3 call_transcriber.py            # вчерашние звонки
  python3 call_transcriber.py --days 3   # за 3 дня
  python3 call_transcriber.py --dry-run  # без записи (тест)

Расписание: планировщик запускает в 02:00 MSK (ночью, не мешает работе).
Стоимость: ~$0.0002/звонок (Gemini Flash аудио). При 262 звонках/день = ~$0.05/день.
"""

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

# ── Пути ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
BASE_DIR   = SCRIPT_DIR.parent
DATA_DIR   = BASE_DIR / "data"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
CACHE_FILE = DATA_DIR / "processed_calls.json"

os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
load_dotenv(BASE_DIR / ".env", override=True)

# ── Конфиг ───────────────────────────────────────────────────────────────────
BITRIX_URL   = (os.getenv("PRODUCTION_BITRIX_WEBHOOK_URL") or
                os.getenv("BITRIX_WEBHOOK_URL", "")).rstrip("/")
GEMINI_KEY   = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"  # актуальная модель с поддержкой аудио
MIN_DURATION = 10      # сек — не транскрибируем совсем короткие
MAX_PER_RUN  = 100     # лимит за один запуск
MSK = timezone(timedelta(hours=3))

# Прокси подхватывается автоматически через HTTPS_PROXY/HTTP_PROXY из .env
# google-genai (httpx) и requests читают эти переменные из os.environ
# Убедитесь что .env содержит: HTTPS_PROXY=socks5://...

# Промпт для Gemini
SYSTEM_PROMPT = """Ты — аналитик телефонных переговоров птицеводческого хозяйства "ВезёмЦыплят" (Крым).
Тебе предоставлена запись звонка (входящий или исходящий) между менеджером и клиентом.

Сделай следующее:

1. **ТРАНСКРИПТ** — полный текст разговора с разбивкой по спикерам:
   - МЕНЕДЖЕР: ...
   - КЛИЕНТ: ...

2. **САММАРИ** — 2-4 предложения: о чём был звонок, что решили.

3. **ВОПРОСЫ КЛИЕНТА** — список вопросов, которые задал клиент (нумерованный).

4. **ДОГОВОРЁННОСТИ** — что обещал менеджер, какие следующие шаги.

5. **ОЦЕНКА МЕНЕДЖЕРА** — по шкале 1-5:
   - Назвал ли себя в начале
   - Выяснил ли город/регион клиента
   - Назвал ли цену с ОПТ-шкалой (не одну цифру)
   - Предложил ли доп. товары
   - Зафиксировал ли следующий шаг

Отвечай только на русском языке. Формат ответа — JSON:
{
  "transcript": "МЕНЕДЖЕР: Алло...\nКЛИЕНТ: ...",
  "summary": "...",
  "client_questions": ["вопрос 1", "вопрос 2"],
  "agreements": ["договорённость 1"],
  "manager_score": {
    "total": 3,
    "named_self": true,
    "asked_city": false,
    "gave_price_scale": true,
    "offered_upsell": false,
    "set_next_step": true
  }
}
"""


# ── Кэш обработанных звонков ─────────────────────────────────────────────────
def load_cache() -> set:
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return set(data.get("processed", []))
        except Exception:
            return set()
    return set()


def save_cache(processed: set):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"processed": list(processed),
                       "updated": datetime.now(MSK).isoformat()},
                      f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  ⚠️ Кэш не сохранён: {e}")


# ── Bitrix API ────────────────────────────────────────────────────────────────
def bitrix_get(method: str, params: dict = None, timeout: int = 60) -> dict:
    url = f"{BITRIX_URL}/{method}.json"
    try:
        resp = requests.get(url, params=params or {}, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
        print(f"  ⚠️ {method}: HTTP {resp.status_code}")
        return {}
    except requests.Timeout:
        print(f"  ⚠️ {method}: таймаут {timeout}с")
        return {}
    except Exception as e:
        print(f"  ⚠️ {method}: {e}")
        return {}


def get_calls_for_period(since: str, until: str) -> list:
    """Получает звонки за период через crm.activity.list (voximplant.statistic.get не работает!).
    
    🔴 FIX: voximplant.statistic.get возвращает старые тестовые звонки за 2019 год.
    Используем crm.activity.list с фильтром по PROVIDER_ID=VOXIMPLANT_CALL.
    """
    all_calls = []
    start = 0
    while True:
        data = bitrix_get("crm.activity.list", {
            "filter[TYPE_ID]": "2",  # Звонок
            "filter[PROVIDER_ID]": "VOXIMPLANT_CALL",
            "filter[>=CREATED]": since,
            "filter[<=CREATED]": until,
            "order[CREATED]": "DESC",
            "start": start,
        }, timeout=60)
        batch = data.get("result", [])
        all_calls.extend(batch)
        if data.get("next") is None or not batch:
            break
        start = data["next"]
        time.sleep(0.5)
    
    # Конвертируем формат crm.activity → voximplant.statistic совместимый
    converted = []
    for call in all_calls:
        files = call.get("FILES", [])
        record_file_id = None
        if files and isinstance(files, list):
            # Извлекаем ID файла из URL: fileId=XXXXXX
            for f in files:
                if isinstance(f, dict):
                    fid = f.get("id")
                    if fid:
                        record_file_id = str(fid)
                        break
        
        # Вычисляем длительность из START_TIME и END_TIME
        duration = 0
        start_time = call.get("START_TIME")
        end_time = call.get("END_TIME")
        if start_time and end_time:
            try:
                from datetime import datetime
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                duration = int((end_dt - start_dt).total_seconds())
            except Exception as e:
                print(f"  ⚠️ Duration calc error: {e}")
        
        # Извлекаем телефон из SUBJECT
        subject = call.get("SUBJECT", "")
        phone = subject
        if "Исходящий на " in subject:
            phone = subject.replace("Исходящий на ", "")
        elif "Входящий от " in subject:
            phone = subject.replace("Входящий от ", "")
        
        converted.append({
            "ID": call.get("ID"),
            "CALL_START_DATE": call.get("CREATED"),
            "CALL_DURATION": duration,
            "PHONE_NUMBER": phone,
            "DIRECTION": "1" if "Входящий" in subject else "2",
            "RECORD_FILE_ID": record_file_id,
            "CRM_ACTIVITY_ID": call.get("ID"),
        })
    
    return converted


def get_download_url(file_id: str) -> str | None:
    """Получает временную ссылку на скачивание MP3."""
    data = bitrix_get("disk.file.get", {"id": file_id}, timeout=30)
    result = data.get("result", {})
    return result.get("DOWNLOAD_URL")


def update_activity_comment(activity_id: str, comment: str):
    """Добавляет саммари в DESCRIPTION активности (звонка)."""
    try:
        requests.get(
            f"{BITRIX_URL}/crm.activity.update.json",
            params={"id": activity_id,
                    "fields[DESCRIPTION]": f"[ИИ-транскрипт]\n{comment}"},
            timeout=30
        )
    except Exception as e:
        print(f"  ⚠️ Не удалось обновить activity {activity_id}: {e}")


# ── Gemini Flash транскрипция ─────────────────────────────────────────────────
def transcribe_audio_gemini(audio_path: str, call_meta: dict) -> dict | None:
    """
    Отправляет аудиофайл в Gemini Flash и получает транскрипт + саммари.
    Использует новый SDK google-genai. Прокси — автоматически через HTTPS_PROXY из .env.
    Возвращает dict или None при ошибке.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("  ❌ google-genai не установлен. Запустите: pip install google-genai 'httpx[socks]'")
        return None

    if not GEMINI_KEY:
        print("  ❌ GEMINI_API_KEY не задан в .env")
        return None

    client = genai.Client(api_key=GEMINI_KEY)
    # Прокси подхватывается через HTTPS_PROXY из os.environ (установлен load_dotenv выше)

    direction = "входящий" if str(call_meta.get("CALL_TYPE")) == "2" else "исходящий"
    phone = call_meta.get("PHONE_NUMBER", "неизвестен")
    duration = int(call_meta.get("CALL_DURATION", 0))

    user_prompt = (
        f"Тип звонка: {direction}\n"
        f"Телефон клиента: {phone}\n"
        f"Длительность: {duration // 60}:{duration % 60:02d}\n"
        f"Дата: {call_meta.get('CALL_START_DATE', '')[:16]}\n\n"
        "Пожалуйста, обработай запись звонка согласно инструкциям."
    )

    try:
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Content(parts=[
                    types.Part(text=SYSTEM_PROMPT + "\n\n" + user_prompt),
                    types.Part(inline_data=types.Blob(
                        mime_type="audio/mp3",
                        data=audio_data,
                    )),
                ])
            ],
        )

        raw = response.text.strip()

        # Пробуем распарсить JSON из ответа
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        result = json.loads(raw)
        return result

    except json.JSONDecodeError:
        # Если Gemini вернул не JSON — сохраняем как raw text
        return {"transcript": raw, "summary": raw[:500], "raw_only": True,
                "client_questions": [], "agreements": [], "manager_score": None}
    except Exception as e:
        print(f"  ❌ Gemini ошибка: {type(e).__name__}: {e}")
        return None


# ── Основной pipeline ─────────────────────────────────────────────────────────
def process_call(call: dict, dry_run: bool = False) -> bool:
    """
    Обрабатывает один звонок: скачивает аудио → транскрибирует → сохраняет.
    Возвращает True при успехе.
    """
    call_id = call.get("ID", "unknown")
    file_id = call.get("RECORD_FILE_ID")
    duration = int(call.get("CALL_DURATION", 0))
    phone = call.get("PHONE_NUMBER", "?")
    date_str = call.get("CALL_START_DATE", "")[:10]

    print(f"\n  📞 Звонок {call_id} | {date_str} | {phone} | {duration}с")

    if not file_id:
        print("     ⏭️ Нет RECORD_FILE_ID — пропуск")
        return False

    # Получаем ссылку на скачивание
    download_url = get_download_url(str(file_id))
    if not download_url:
        print("     ⚠️ Не удалось получить DOWNLOAD_URL")
        return False

    if dry_run:
        print("     🔍 DRY-RUN: URL получен, транскрипция пропущена")
        return True

    # Скачиваем аудио во временный файл
    try:
        resp = requests.get(download_url, timeout=60, stream=True)
        if resp.status_code != 200:
            print(f"     ⚠️ Скачивание: HTTP {resp.status_code}")
            return False

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            for chunk in resp.iter_content(chunk_size=8192):
                tmp.write(chunk)
            tmp_path = tmp.name

        size_kb = os.path.getsize(tmp_path) / 1024
        print(f"     ✅ Скачано: {size_kb:.0f} KB")

    except Exception as e:
        print(f"     ❌ Ошибка скачивания: {e}")
        return False

    # Транскрибируем
    print("     🤖 Транскрибирую через Gemini Flash...")
    result = transcribe_audio_gemini(tmp_path, call)

    # Удаляем временный файл
    try:
        os.unlink(tmp_path)
    except Exception:
        pass

    if not result:
        return False

    # Формируем итоговую запись
    record = {
        "call_id": call_id,
        "call_date": call.get("CALL_START_DATE"),
        "phone": phone,
        "duration_sec": duration,
        "direction": "incoming" if str(call.get("CALL_TYPE")) == "2" else "outgoing",
        "crm_entity_type": call.get("CRM_ENTITY_TYPE"),
        "crm_entity_id": call.get("CRM_ENTITY_ID"),
        "crm_activity_id": call.get("CRM_ACTIVITY_ID"),
        "manager_user_id": call.get("PORTAL_USER_ID"),
        "processed_at": datetime.now(MSK).isoformat(),
        **result,
    }

    # Сохраняем
    day_dir = TRANSCRIPT_DIR / date_str
    os.makedirs(day_dir, exist_ok=True)
    out_file = day_dir / f"call_{call_id}.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    print(f"     💾 Сохранено: {out_file.name}")
    print(f"     📝 Саммари: {result.get('summary', '')[:120]}")

    return True


def run(days_back: int = 1, dry_run: bool = False):
    """Основной запуск транскрибатора."""
    now = datetime.now(MSK)
    since_dt = (now - timedelta(days=days_back)).replace(hour=0, minute=0, second=0)
    until_dt = now.replace(hour=23, minute=59, second=59)

    since = since_dt.strftime("%Y-%m-%dT%H:%M:%S")
    until = until_dt.strftime("%Y-%m-%dT%H:%M:%S")

    print(f"\n{'='*55}")
    print(f"📞 CALL TRANSCRIBER — {now.strftime('%Y-%m-%d %H:%M MSK')}")
    print(f"   Период: {since[:10]} → {until[:10]}")
    print(f"   Мин. длительность: {MIN_DURATION}с")
    print(f"   Dry-run: {dry_run}")
    print(f"{'='*55}\n")

    if not BITRIX_URL:
        print("❌ BITRIX_WEBHOOK_URL не настроен!")
        sys.exit(1)

    # Загружаем кэш
    processed = load_cache()
    print(f"📋 Уже обработано ранее: {len(processed)} звонков")

    # Получаем звонки
    print("\n🔍 Получаю звонки из Bitrix...")
    all_calls = get_calls_for_period(since, until)
    print(f"   Всего звонков за период: {len(all_calls)}")

    # Фильтрация
    candidates = [
        c for c in all_calls
        if int(c.get("CALL_DURATION", 0)) >= MIN_DURATION
        and c.get("RECORD_FILE_ID")
        and str(c.get("ID")) not in processed
    ]
    print(f"   К обработке (>={MIN_DURATION}с, с записью, новые): {len(candidates)}")

    if not candidates:
        print("\n✅ Нет новых звонков для транскрипции.")
        return

    # Ограничение за запуск
    if len(candidates) > MAX_PER_RUN:
        print(f"   ⚠️ Ограничение: обрабатываю первые {MAX_PER_RUN} из {len(candidates)}")
        candidates = candidates[:MAX_PER_RUN]

    # Обрабатываем
    success = 0
    failed  = 0

    for i, call in enumerate(candidates, 1):
        print(f"\n[{i}/{len(candidates)}]", end="")
        if process_call(call, dry_run=dry_run):
            if not dry_run:
                processed.add(str(call.get("ID")))
            success += 1
        else:
            failed += 1
        # Пауза между запросами к Gemini (rate limit)
        if i < len(candidates):
            time.sleep(2)

    # Сохраняем кэш
    if not dry_run:
        save_cache(processed)

    # Итог
    print(f"\n{'='*55}")
    print(f"✅ Готово! Успешно: {success} | Ошибок: {failed}")
    print(f"💰 Примерная стоимость: ${success * 0.0002:.4f}")
    total_saved = sum(1 for d in TRANSCRIPT_DIR.iterdir() if d.is_dir()
                      for _ in d.glob("*.json"))
    print(f"📁 Всего транскриптов в базе: {total_saved}")
    print(f"{'='*55}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Транскрибатор звонков ВезёмЦыплят")
    parser.add_argument("--days",    type=int, default=1,
                        help="За сколько дней обрабатывать (default: 1 = вчера+сегодня)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Тест без транскрипции (проверяет доступность файлов)")
    args = parser.parse_args()

    run(days_back=args.days, dry_run=args.dry_run)
