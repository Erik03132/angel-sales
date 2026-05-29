import json
import os
import re
import re as _re_core
import time
import traceback

import requests
from feed_calculator import process_feed_query
from hybrid_search import bm25_search
from memory_graph import MemoryGraph
from sales_logic import apply_sales_layer, resolve_breed_synonyms
from tool_digest import digest_product_context, digest_vector_context
from vector_memory import VectorMemory

# RAG Lite — экспертные знания из PDF-библиотеки птицеводства
try:
    from rag_lite import format_context_for_llm, search_knowledge
    print("✅ RAG Lite подключён")
except ImportError:
    search_knowledge = None
    format_context_for_llm = None
    print("⚠️ RAG Lite недоступен (rag_lite.py не найден)")

# === РОЛЕВАЯ МОДЕЛЬ ===
ROLE_CREATOR  = "creator"   # Игорь — создатель системы
ROLE_BOSS     = "boss"      # Андрей — руководитель бизнеса
ROLE_EMPLOYEE = "employee"  # Сотрудник/менеджер
ROLE_CUSTOMER = "customer"  # Клиент

# ID известных пользователей (читается из .env — единый источник истины)
_CREATOR_TG_ID = str(os.getenv("ADMIN_TELEGRAM_ID", "176203333")).strip()

def detect_role(query: str, sender_id: str = None, sender_name: str = None) -> str:
    """Определяет роль пользователя по его Telegram ID и имени.
    Приоритет: creator → boss (из roles_config.json) → employee → customer
    """
    sid = str(sender_id) if sender_id else ""

    # 1. Создатель системы
    if sid == _CREATOR_TG_ID:
        return ROLE_CREATOR

    # 2. Загружаем roles_config.json для определения boss/employee
    try:
        _roles_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "roles_config.json"
        )
        if os.path.exists(_roles_path):
            with open(_roles_path, "r", encoding="utf-8") as _f:
                _cfg = json.load(_f)
            user_entry = _cfg.get("users", {}).get(sid, {})
            user_role = user_entry.get("role", _cfg.get("default_role", "manager"))
            if user_role == "owner":
                return ROLE_BOSS
            elif user_role in ("manager", "employee"):
                return ROLE_EMPLOYEE
    except json.JSONDecodeError as _e:
        print(f"⚠️ detect_role: битый JSON в roles_config.json: {_e}")
        _cfg = {}
    except (FileNotFoundError, PermissionError) as _e:
        print(f"⚠️ detect_role: нет доступа к roles_config.json: {_e}")
    except Exception as _e:
        print(f"⚠️ detect_role: ошибка чтения roles_config: {_e}")
        traceback.print_exc()

    # 3. По умолчанию — клиент
    return ROLE_CUSTOMER

# Паттерн для определения телефона в истории диалога
# (Phone-First Protocol)
_PHONE_PATTERN = _re_core.compile(
    r'(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}'
)

def _has_phone_in_history(history: list, current_query: str = "") -> bool:
    """Проверяет, оставил ли клиент телефон в истории диалога.
    Phone-First Protocol: корм и допы предлагаем ТОЛЬКО после получения телефона.
    """
    # Проверяем текущее сообщение
    if _PHONE_PATTERN.search(current_query):
        return True
    # Проверяем историю
    if history:
        for msg in history:
            text = ""
            contact_phone = None
            if isinstance(msg, dict):
                parts = msg.get("parts", [])
                if isinstance(parts, list) and parts:
                    text = str(parts[0])
                else:
                    text = msg.get("content", "")
                contact = msg.get("contact")
                if contact and isinstance(contact, dict):
                    contact_phone = contact.get("phone_number") or contact.get("phone")
            if _PHONE_PATTERN.search(str(text)) or (contact_phone and _PHONE_PATTERN.search(str(contact_phone))):
                return True
    return False

# Загружаем настройки
from dotenv import load_dotenv

# Определяем базовую директорию проекта (абсолютный путь)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# ─── Живой прайс-лист из config/prices.json ─────────────────────────────────
# F7: цены больше не хардкодятся — читаются из файла (обновляется price_updater.py)
_PRICES_JSON_PATH = os.path.join(BASE_DIR, 'config', 'prices.json')
_prices_cache = {"data": None, "mtime": 0}

def load_price_list() -> str:
    """Загружает прайс из config/prices.json и форматирует в текст для промпта.
    Кэш сбрасывается если файл изменился (price_updater.py обновил цены).
    """
    global _prices_cache
    try:
        mtime = os.path.getmtime(_PRICES_JSON_PATH)
        if _prices_cache["data"] is None or mtime != _prices_cache["mtime"]:
            with open(_PRICES_JSON_PATH, 'r', encoding='utf-8') as f:
                _prices_cache["data"] = json.load(f)
            _prices_cache["mtime"] = mtime
            updated = _prices_cache["data"].get("_meta", {}).get("updated_at", "?")
            print(f"✅ Прайс-лист загружен из prices.json (обновлён: {updated})")
    except Exception as e:
        print(f"⚠️ prices.json не найден — используем пустой прайс: {e}")
        return ""

    data = _prices_cache["data"]
    lines = []
    for cat_key, cat in data.get("categories", {}).items():
        label = cat.get("label", cat_key.upper())
        min_ord = cat.get("min_order", 1)
        lines.append(f"{label} (мин. {min_ord} гол.):")
        for name, item in cat.get("items", {}).items():
            if "prices" in item:  # тарифная сетка (бройлеры)
                tiers = ", ".join(f"от {p['from']}шт={p['price']}₽" for p in item["prices"])
                lines.append(f"  {name}: {tiers}")
            elif "price" in item:
                lines.append(f"  {name}={item['price']}₽")
        lines.append("")

    delivery = data.get("delivery", {})
    if delivery:
        lines.append(f"Доставка: {delivery.get('days', '')} по {delivery.get('geography', '')}. {delivery.get('transport', '')}.")
        lines.append(f"Самовывоз: {delivery.get('pickup_address', '')}")

    return "\n".join(lines)


def load_schedule_context(query: str = "", month: int = None) -> str:
    """
    Возвращает текстовый блок с графиком вывода для использования в промпте.
    Если query содержит породу или месяц — фильтрует под запрос.
    Иначе — показывает ближайшие 2 месяца.
    """
    try:
        with open(_PRICES_JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return ""

    schedule = data.get("schedule", {})
    if not schedule:
        return ""

    from datetime import datetime
    now = datetime.now()
    cur_month = month or now.month
    cur_year = now.year

    # Ключевые слова пород → ключи в schedule
    _breed_keys = {
        "кобб": "broilers", "росс": "broilers", "бройлер": "broilers",
        "мастер": "broilers_color", "ред бро": "broilers_color", "цветной": "broilers_color",
        "мясояичн": "meat_egg", "кучинск": "meat_egg",
        "ломан": "loman_brown", "хайсекс": "highsex_brown",
        "доминант": "dominant", "адлерск": "adler",
        "индюш": "turkeys", "биг": "turkeys",
        "мулард": "mulard",
        "агидель": "ducks_ru", "голубой фавор": "ducks_ru",
        "гусят": "geese", "линд": "geese",
        "цесар": "guinea_fowl",
    }

    # Определяем какие ключи нужны по запросу
    q = query.lower()
    target_keys = []
    for kw, key in _breed_keys.items():
        if kw in q and key not in target_keys:  # дедупликация
            target_keys.append(key)

    # Если порода не найдена — показываем все на ближайшие 2 месяца
    if not target_keys:
        target_keys = [k for k in schedule.keys() if k != "_meta"]

    lines = ["📅 ГРАФИК ВЫВОДА (incubird.ru, обновлён 14.01.2026):"]
    meta_note = schedule.get("_meta", {}).get("note", "")
    if meta_note:
        lines.append(f"   {meta_note}")

    found_any = False
    for key in target_keys:
        entry = schedule.get(key, {})
        if not isinstance(entry, dict):
            continue
        label = entry.get("label", key)
        months_data = entry.get("months", {})
        note = entry.get("note", "")

        # Ближайшие даты (текущий + следующий месяц)
        upcoming = []
        for offset in range(3):
            m = ((cur_month - 1 + offset) % 12) + 1
            y = cur_year + ((cur_month - 1 + offset) // 12)
            dates = months_data.get(str(m), [])
            if dates:
                month_name = ["янв", "фев", "мар", "апр", "май", "июн",
                              "июл", "авг", "сен", "окт", "ноя", "дек"][m - 1]
                upcoming.append(f"{month_name}: {', '.join(str(d) for d in dates)}")

        if upcoming:
            lines.append(f"  🐣 {label}: {' | '.join(upcoming)}")
            found_any = True
        elif note:
            lines.append(f"  ⛔ {label}: {note}")
            found_any = True

    if not found_any:
        return ""

    return "\n".join(lines)


# Паттерн для извлечения цен из текста клиента
_PRICE_IN_TEXT = re.compile(r'(\d{2,4})\s*(?:руб|₽|р\.?)\b', re.IGNORECASE)

def detect_price_conflicts(query: str) -> str:
    """
    Сравнивает цену упомянутую клиентом с нашей базой из prices.json.
    Если расхождение > 10% — возвращает предупреждение со ссылкой на источники.
    Возвращает пустую строку если всё OK.
    """
    mentioned_prices = [int(m) for m in _PRICE_IN_TEXT.findall(query)]
    if not mentioned_prices:
        return ""

    try:
        with open(_PRICES_JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return ""

    meta = data.get("_meta", {})
    updated_at = meta.get("updated_at", "?")
    source = meta.get("primary_source", "VK incubird")

    conflicts = []
    categories = data.get("categories", {})

    q_lower = query.lower()
    for cat_key, cat_data in categories.items():
        for item_name, item_data in cat_data.get("items", {}).items():
            # Нечёткий матч: первые 4 символа первого слова ("линд" → "линдовских")
            name_lower = item_name.lower().split()[0]
            name_key = name_lower[:4]
            if len(name_key) < 3 or name_key not in q_lower:
                continue
            our_price = item_data.get("price")
            if not our_price:
                continue
            for client_price in mentioned_prices:
                diff_pct = abs(client_price - our_price) / our_price * 100
                if diff_pct > 10:
                    conflicts.append(
                        f"• {item_name}: клиент назвал {client_price}₽, "
                        f"в нашей базе {our_price}₽ "
                        f"(источник: {source}, обновлено {updated_at[:10]})"
                    )

    if not conflicts:
        return ""

    warning = (
        "⚠️ ВНИМАНИЕ — ПРОТИВОРЕЧИЕ В ЦЕНАХ:\n"
        + "\n".join(conflicts)
        + "\n→ Сообщи клиенту актуальную цену из базы. "
        "Если он настаивает — порекомендуй уточнить у менеджера."
    )
    return warning

load_dotenv(override=True)

# Если ключей нет локально, пробуем найти их в родительской папке
if not os.getenv("OPENROUTER_API_KEY"):
    load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

OPENROUTER_KEY = (os.getenv("OPENROUTER_API_KEY") or "").strip() or None
# PERPLEXITY_KEY загружается локально в call_perplexity_search()
NEON_DATABASE_URL = os.getenv("NEON_DATABASE_URL")
# GEMINI_API_KEY сохранён только для call_analyzer (аудио-транскрипция)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_PRO_API_KEY")

# --- Каскадный LLM-движок ---
# Приоритет 1: OpenRouter  — основной (deepseek, claude, и др.)
# Приоритет 2: Ollama/Gemma4 — оффлайн-страховка
# Поиск: Perplexity (ОБЯЗАТЕЛЬНО для всех интернет-запросов)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e2b")

# --- ПЕРСОНАЖИ ---
PERSONA_ZABOTKINA = "zabotkina"     # Главная (отчёты, аудит менеджеров)
PERSONA_PTENCHIKOVA = "ptenchikova" # Песочница (планы, развитие, задачи)

def get_current_persona():
    """Определяет текущую личность Анжелы на основе окружения."""
    sandbox_url = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "")
    current_url = os.getenv("BITRIX_WEBHOOK_URL", "")
    if sandbox_url and (sandbox_url in current_url or "mjxvhq" in current_url):
        return PERSONA_PTENCHIKOVA
    return PERSONA_ZABOTKINA

def get_persona_prompt_info(persona=None):
    """Возвращает данные для системного промпта в зависимости от личности."""
    p = persona or get_current_persona()
    from datetime import datetime

    from daily_report import get_dynamic_crm_report, get_dynamic_sandbox_report
    
    today_str = datetime.now().strftime("%d.%m.%Y")
    
    if p == PERSONA_PTENCHIKOVA:
        return {
            "is_ptenchikova": True,
            "name": "Анжела Птенчикова",
            "surname": "Птенчикова",
            "company": "Песочница IncuBird (Маркетинг и Продвижение)",
            "report_data": get_dynamic_sandbox_report(),
            "today": today_str,
            "focus": "продвижение сайтов, SEO, статьи для Я.Дзен, создание постов в ВК, ведение задач, эксперименты"
        }
    else:
        return {
            "is_ptenchikova": False,
            "name": "Анжела Заботкина",
            "surname": "Заботкина",
            "company": "Азовский инкубатор (Production)",
            "report_data": get_dynamic_crm_report(),
            "today": today_str,
            "focus": "аудит продаж, анализ показателей CRM, контроль менеджеров, отчетность, консультирование клиентов по продажам птицы"
        }

def call_perplexity_search(query: str) -> str:
    """Поиск через Perplexity Sonar — ОБЯЗАТЕЛЬНЫЙ инструмент для интернет-запросов.
    Используется когда нужна актуальная информация из сети.
    """
    perplexity_key = (os.getenv("PERPLEXITY_API_KEY") or "").strip()
    if not perplexity_key:
        print("⚠️ PERPLEXITY_API_KEY не задан, поиск недоступен")
        return ""
    try:
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {perplexity_key}", "Content-Type": "application/json"},
            json={
                "model": "sonar",
                "messages": [{"role": "user", "content": query}],
                "max_tokens": 1024,
            },
            timeout=30,
            proxies={"http": None, "https": None}
        )
        try:
            data = resp.json()
        except (ValueError, KeyError) as json_err:
            print(f"⚠️ Perplexity: JSON parse error — {json_err}")
            return ""
        if data.get("choices") and len(data["choices"]) > 0:
            result = data["choices"][0]["message"]["content"]
            print(f"🔍 Perplexity: {len(result)} символов")
            return result
        print(f"⚠️ Perplexity error: {data.get('error', data)}")
        return ""
    except Exception as e:
        print(f"⚠️ Perplexity failed: {e}")
        return ""

# ============================================================
# 🧠 УМНЫЙ КАСКАД v2 — маршрутизация по сложности запроса
# ============================================================
# Простые вопросы → дешёвая/бесплатная модель (экономия)
# Сложные вопросы → топ-модель (качество)
#
# Тиры:
#   LITE  — FAQ, приветствия, цены, расписание     → $0.11/M  
#   STD   — продажи, консультации, RAG             → $0.43/M  
#   PRO   — жалобы, переговоры, сложная логика     → $0.73/M  
# ============================================================

# Модели по тирам (каждый тир — каскад с фоллбэками)
_TIER_MODELS = {
    "lite": [
        "deepseek/deepseek-v4-flash",                # $0.11/$0.22 — 1048K, быстрая
        "deepseek/deepseek-v4-flash:free",            # Бесплатная (фоллбэк)
        "qwen/qwen3.6-flash",                         # $0.19/$1.12 — 1000K
    ],
    "std": [
        "deepseek/deepseek-v4-pro",                   # $0.43/$0.87 — 1048K, умная
        "moonshotai/kimi-k2.6",                       # $0.73/$3.49 — 262K, Kimi K2.6
        "deepseek/deepseek-v4-flash",                 # Фоллбэк на быструю
    ],
    "pro": [
        "moonshotai/kimi-k2.6",                       # $0.73/$3.49 — 262K, топ-качество
        "deepseek/deepseek-v4-pro",                   # $0.43/$0.87 — фоллбэк
        "anthropic/claude-sonnet-4.6",                # $3/$15 — крайний резерв
    ],
}

# Ключевые слова для быстрой классификации сложности
_LITE_KEYWORDS = {
    "привет", "здравствуйте", "добрый день", "добрый вечер", "доброе утро",
    "цена", "стоимость", "сколько стоит", "прайс", "цены",
    "доставка", "когда доставка", "сроки", "когда привезут",
    "есть в наличии", "наличие", "остаток", "сколько есть",
    "контакты", "телефон", "адрес", "где находитесь",
    "график", "режим работы", "когда работаете",
    "спасибо", "благодарю", "ок", "хорошо", "понял", "ясно",
    "да", "нет", "ладно", "договорились",
}

_PRO_KEYWORDS = {
    "жалоба", "претензия", "плохо", "дохнут", "падёж", "мор",
    "обман", "кинули", "некачественный", "больные", "заболели",
    "возврат", "вернуть деньги", "компенсация",
    "скидка", "торг", "дорого", "дешевле", "снизить цену",
    "оптом", "крупная партия", "тысяча", "10000", "5000",
    "конкурент", "другой поставщик", "у других дешевле",
    "юрлицо", "договор", "счёт-фактура", "накладная", "НДС",
}


def _classify_complexity(prompt: str, history=None) -> str:
    """Классифицирует сложность запроса → 'lite' | 'std' | 'pro'."""
    text = prompt.lower().strip()
    
    # Короткие сообщения (< 15 символов) — почти всегда lite
    if len(text) < 15:
        return "lite"
    
    # Проверяем PRO-маркеры (приоритет над lite)
    for kw in _PRO_KEYWORDS:
        if kw in text:
            return "pro"
    
    # Проверяем LITE-маркеры
    for kw in _LITE_KEYWORDS:
        if kw in text:
            return "lite"
    
    # Длинная история (>8 сообщений) → скорее всего сложный диалог
    if history and len(history) > 8:
        return "pro"
    
    # По умолчанию — стандарт
    return "std"


def _call_openrouter(prompt, history=None, system_prompt=None, tier=None):
    """Вызов через OpenRouter с маршрутизацией по сложности."""
    if not OPENROUTER_KEY or not OPENROUTER_KEY.strip():
        print("⚠️ OPENROUTER_API_KEY не задан!")
        return None

    saved_proxies = {}
    for key in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
        if key in os.environ:
            saved_proxies[key] = os.environ.pop(key)
    
    messages = []
    # System prompt отдельным сообщением — КРИТИЧНО для следования инструкциям
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    
    # Конвертируем историю Gemini-формата в OpenAI-формат
    if history:
        for msg in history:
            role = "assistant" if msg.get("role") == "model" else msg.get("role", "user")
            content = msg.get("parts", [msg.get("content", "")])[0] if isinstance(msg.get("parts"), list) else msg.get("content", "")
            messages.append({"role": role, "content": content})
    
    messages.append({"role": "user", "content": prompt})
    
    # Определяем тир если не задан
    if tier is None:
        tier = _classify_complexity(prompt, history)
    
    or_models = _TIER_MODELS.get(tier, _TIER_MODELS["std"])
    print(f"🎯 Тир: {tier.upper()} → модели: {[m.split('/')[-1] for m in or_models]}")
    
    try:
        for model_name in or_models:
            try:
                resp = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
                    json={"model": model_name, "messages": messages, "max_tokens": 4096},
                    timeout=45,
                    proxies={"http": None, "https": None}  # Явно отключаем прокси
                )
                try:
                    data = resp.json()
                except (ValueError, KeyError) as json_err:
                    print(f"⚠️ OpenRouter {model_name}: JSON parse error — {json_err}")
                    continue
                if data.get("choices") and len(data["choices"]) > 0:
                    print(f"✅ LLM: {model_name} (tier={tier})")
                    return data["choices"][0]["message"]["content"]
                else:
                    print(f"⚠️ OpenRouter {model_name}: {data.get('error', 'Unknown error')}")
            except Exception as e:
                print(f"⚠️ OpenRouter {model_name} exception: {e}")
        
        return None
    finally:
        # Восстанавливаем прокси (если были)
        for key, val in saved_proxies.items():
            os.environ[key] = val

def _call_ollama_local(prompt, history=None):
    """Оффлайн-фоллбэк: Gemma4 через Ollama (работает БЕЗ интернета)"""
    try:
        messages = []
        if history:
            for msg in history:
                role = "assistant" if msg.get("role") == "model" else msg.get("role", "user")
                content = msg.get("parts", [msg.get("content", "")])[0] if isinstance(msg.get("parts"), list) else msg.get("content", "")
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": prompt})

        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": OLLAMA_MODEL, "messages": messages, "stream": False},
            timeout=120  # Gemma4 на CPU может думать долго
        )
        data = resp.json()
        if "message" in data and "content" in data["message"]:
            print(f"✅ Ollama/{OLLAMA_MODEL} ответила (offline mode)")
            return data["message"]["content"]
        else:
            print(f"⚠️ Ollama unexpected response: {data}")
            return None
    except requests.exceptions.ConnectionError:
        print("⚠️ Ollama не запущена (http://localhost:11434 недоступен)")
        return None
    except Exception as e:
        print(f"⚠️ Ollama/{OLLAMA_MODEL} failed: {e}")
        return None

def call_llm(prompt, history=None, system_prompt=None, tier=None):
    """Каскадный вызов с умной маршрутизацией:
    1. Классификация сложности → LITE / STD / PRO
    2. Подбор модели по тиру
    3. Фоллбэк на Ollama (оффлайн)
    
    tier можно задать явно: 'lite', 'std', 'pro'
    """
    # Шаг 1: OpenRouter — основной LLM с маршрутизацией
    result = _call_openrouter(prompt, history, system_prompt=system_prompt, tier=tier)
    if result:
        return result

    # Шаг 2: Оффлайн-страховка — Gemma4 через Ollama
    print("🔌 OpenRouter недоступен. Переключаюсь на Gemma4 (оффлайн)...")
    result = _call_ollama_local(prompt, history)
    if result:
        return result

    return "Прости, у меня сейчас технические неполадки... Напиши мне через пару минут! 🐣"

# --- Векторный поиск (с graceful degradation) ---
vdb = None
try:
    from vector_db import AngelochkaVectorDB
    vdb = AngelochkaVectorDB()
    if not vdb.enabled:
        vdb = None
        print("⚠️ VectorDB отключена (нет подключения к Neon)")
except Exception as e:
    print(f"⚠️ VectorDB недоступна: {e}")

# --- Phase 1+2: Граф памяти клиентов + Векторный поиск Gemini Embedding 2 ---
_memory_graph = None
try:
    _memory_graph = MemoryGraph()
    stats = _memory_graph.stats()
    print(f"✅ Граф памяти: {stats['active_nodes']} узлов, {stats['unique_clients']} клиентов")
except Exception as e:
    print(f"⚠️ Граф памяти недоступен: {e}")

_vector_mem = None
try:
    _vector_mem = VectorMemory()
    stats = _vector_mem.stats()
    if stats['total_vectors'] > 0:
        print(f"✅ Векторный поиск: {stats['total_vectors']} эмбеддингов ({stats['model']})")
    else:
        print("ℹ️ Векторный индекс пуст (запустите индексацию)")
except Exception as e:
    print(f"⚠️ Векторный поиск недоступен: {e}")

# --- Предзагрузка файлов данных (один раз при старте) ---
_faq_cache = {}
_faq_path = os.path.join(DATA_DIR, 'faq_cache.json')
if os.path.exists(_faq_path):
    with open(_faq_path, 'r', encoding='utf-8') as f:
        _faq_cache = json.load(f)
    print(f"✅ FAQ cache загружен: {len(_faq_cache)} записей")

# --- Smart FAQ: Автовыпускающийся кэш ---
import re as _re


class SmartFAQ:
    """Умный FAQ: вопросы, которые задают 3+ раз, автоматически кэшируются
    с КАЧЕСТВЕННЫМ ответом от LLM (не шаблонным!).
    
    Логика:
    1. Каждый вопрос нормализуется в 'отпечаток' (fingerprint)
    2. Счётчик считает сколько раз похожий вопрос задавался
    3. При 3-м повторении: LLM-ответ сохраняется как эталонный кэш
    4. С 4-го раза: мгновенный ответ из кэша (0ms вместо 3-5с)
    """
    
    PROMOTE_THRESHOLD = 3  # Сколько раз спросить, чтобы попасть в кэш
    
    def __init__(self, cache_dir):
        self._counter_path = os.path.join(cache_dir, 'smart_faq_counter.json')
        self._cache_path = os.path.join(cache_dir, 'smart_faq_cache.json')
        self._counter = {}   # fingerprint → {count, last_query, last_answer}
        self._cache = {}     # fingerprint → quality_answer
        self._load()
    
    def _load(self):
        if os.path.exists(self._counter_path):
            with open(self._counter_path, 'r', encoding='utf-8') as f:
                self._counter = json.load(f)
        if os.path.exists(self._cache_path):
            with open(self._cache_path, 'r', encoding='utf-8') as f:
                self._cache = json.load(f)
        cached = len(self._cache)
        tracked = len(self._counter)
        if cached or tracked:
            print(f"✅ SmartFAQ: {cached} в кэше, {tracked} отслеживается")
    
    def _save(self):
        try:
            with open(self._counter_path, 'w', encoding='utf-8') as f:
                json.dump(self._counter, f, ensure_ascii=False, indent=2)
            with open(self._cache_path, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ SmartFAQ save error: {e}")
    
    def fingerprint(self, query):
        """Нормализует вопрос в 'отпечаток' для группировки похожих.
        'Какие цыплята есть?' и 'какие есть цыплята?' → один отпечаток."""
        q = query.lower().strip()
        # Убираем знаки препинания
        q = _re.sub(r'[^а-яёa-z0-9\s]', '', q)
        # Убираем шум-слова
        noise = {'а', 'и', 'в', 'на', 'у', 'вас', 'ваш', 'ваши', 'мне', 'мой',
                 'ли', 'бы', 'же', 'то', 'не', 'да', 'нет', 'как', 'что',
                 'есть', 'это', 'вот', 'ещё', 'еще', 'уже', 'или', 'но',
                 'здравствуйте', 'добрый', 'день', 'привет', 'пожалуйста',
                 'подскажите', 'скажите', 'можно'}
        words = sorted(set(w for w in q.split() if w not in noise and len(w) > 2))
        return ' '.join(words[:8])  # Макс 8 ключевых слов
    
    def lookup(self, query):
        """Ищет ответ в кэше. Возвращает ответ или None."""
        fp = self.fingerprint(query)
        if not fp or len(fp) < 5:
            return None
        return self._cache.get(fp)
    
    def track(self, query, llm_answer):
        """Отслеживает вопрос. Если задан 3+ раз — кэширует лучший ответ."""
        fp = self.fingerprint(query)
        if not fp or len(fp) < 5 or len(llm_answer) < 50:
            return
        
        if fp not in self._counter:
            self._counter[fp] = {'count': 0, 'last_query': query, 'last_answer': ''}
        
        entry = self._counter[fp]
        entry['count'] += 1
        entry['last_query'] = query
        
        # Сохраняем ЛУЧШИЙ ответ (самый длинный и содержательный)
        if len(llm_answer) > len(entry.get('last_answer', '')):
            entry['last_answer'] = llm_answer
        
        # ВЫПУСК В КЭШ при достижении порога
        if entry['count'] >= self.PROMOTE_THRESHOLD and fp not in self._cache:
            self._cache[fp] = entry['last_answer']
            print(f"🎓 SmartFAQ: ВЫПУСК! '{fp}' → кэш ({entry['count']} повторений)")
        
        self._save()

smart_faq = SmartFAQ(DATA_DIR)


_wisdom = ""
_wisdom_path = os.path.join(DATA_DIR, 'expert_knowledge.md')
if os.path.exists(_wisdom_path):
    with open(_wisdom_path, 'r', encoding='utf-8') as f:
        _wisdom = f.read()
    print(f"✅ Expert knowledge загружен: {len(_wisdom)} символов")

# Загружаем последний скан Битрикс24 (теперь ДИНАМИЧЕСКИ)
def get_dynamic_crm_report():
    try:
        from daily_report import build_report_text, get_latest_scan
        scan = get_latest_scan()
        if scan:
            return build_report_text(scan)
    except Exception as e:
        print(f"⚠️ Ошибка загрузки свежего скана: {e}")
    return "Свежих данных нет."

# Загружаем unified brain как дополнительный контекст
_product_catalog = ""
_brain_path = os.path.join(DATA_DIR, 'angelochka_unified_brain.json')
if os.path.exists(_brain_path):
    with open(_brain_path, 'r', encoding='utf-8') as f:
        brain_data = json.load(f)
        # Формируем компактный текстовый каталог
        products = []
        for item in brain_data:
            if item.get("metadata", {}).get("type") == "product":
                products.append(item["content"])
        _product_catalog = "\n".join(products)
    print(f"✅ Unified Brain загружен: {len(brain_data)} элементов, {len(products)} товаров")

# Загружаем SKILL.md для обогащения промпта
_skill_instructions = ""
_skill_path = os.path.join(BASE_DIR, '.agent', 'skills', 'angelochka-sales', 'SKILL.md')
if os.path.exists(_skill_path):
    with open(_skill_path, 'r', encoding='utf-8') as f:
        _skill_instructions = f.read()
    print(f"✅ Sales Skill загружен: {len(_skill_instructions)} символов")


# --- RAG: поиск товаров из Unified Brain (BM25) ---
_product_items = []
_product_bm25 = None
if _product_catalog:
    import re as _re_prod
    _product_items = [p.strip() for p in _product_catalog.split("\n") if p.strip()]
    try:
        from rank_bm25 import BM25Okapi
        _prod_tokenized = [_re_prod.findall(r'\w+', item.lower()) for item in _product_items]
        _product_bm25 = BM25Okapi(_prod_tokenized)
        print(f"✅ Каталог товаров BM25: {len(_product_items)} позиций")
    except Exception as e:
        print(f"⚠️ BM25 каталог не загружен: {e}")


def get_products_context(query):
    """Поиск товаров по каталогу Unified Brain (BM25 + синонимы + подстрока)."""
    if not _product_items:
        return ""
    
    import re as _re_q
    
    # Синонимы для нечёткого поиска
    _SYNONYMS = {
        "гусята": "гусь гусенок гуси",
        "гусёнок": "гусь гусенок гуси",
        "гуси": "гусь гусенок",
        "утята": "утка утки мускусная индоутка муллард",
        "утки": "утка муллард мускусная индоутка",
        "цыплята": "кобб росс бройлер доминант",
        "бройлеры": "кобб росс бройлер",
        "цыплёнок": "кобб росс бройлер доминант",
        "индюки": "биг индюк индюшата",
        "индюшата": "биг индюк индюшата",
        "несушки": "доминант ломан браун несушка",
        "куры": "доминант ломан браун несушка бройлер",
    }
    
    tokens = _re_q.findall(r'\w+', query.lower())
    if not tokens:
        return ""
    
    # Расширяем запрос синонимами
    expanded = list(tokens)
    for t in tokens:
        if t in _SYNONYMS:
            expanded.extend(_SYNONYMS[t].split())
    
    results = []
    
    # 1. BM25 поиск
    if _product_bm25:
        scores = _product_bm25.get_scores(expanded)
        indexed = [(i, s) for i, s in enumerate(scores) if s > 0.5]
        indexed.sort(key=lambda x: -x[1])
        results = indexed[:7]
    
    # 2. Fallback: поиск по подстроке (если BM25 не нашёл)
    if not results:
        for i, item in enumerate(_product_items):
            item_lower = item.lower()
            for t in expanded:
                if len(t) >= 3 and t in item_lower:
                    results.append((i, 1.0))
                    break
        results = results[:7]
    
    # Фильтр: НЕ показывать корма/аптечку/служебные клиентам
    _EXCLUDE_PATTERNS = [
        "purina", "agravis", "аптечка", "доставка клиенту", "коробка",
        "тест", "предоплата", "позиция удалена", "заморозка"
    ]
    
    if not results:
        return ""
    
    # Фильтруем результаты
    filtered = []
    for idx, score in results:
        item_lower = _product_items[idx].lower()
        if not any(excl in item_lower for excl in _EXCLUDE_PATTERNS):
            filtered.append((idx, score))
    
    if not filtered:
        return ""
    
    lines = ["📦 КАТАЛОГ ТОВАРОВ (актуальные данные):"]
    for i, (idx, _score) in enumerate(filtered, 1):
        lines.append(f"  {i}. {_product_items[idx]}")
    
    result = "\n".join(lines)
    print(f"📦 Каталог: {len(filtered)} товаров найдено")
    return result

def _build_prompt_for_role(role, query, role_context, db_context, vector_context, feed_calc_result, history=None, channel="website"):
    """Строит системный промпт в зависимости от роли."""
    p_info = get_persona_prompt_info()
    is_pten = p_info.get("is_ptenchikova", False)
    data_label = "АКТУАЛЬНЫЕ ЗАДАЧИ В ПЕСОЧНИЦЕ" if is_pten else "ДАННЫЕ ИЗ CRM (РЕАЛЬНЫЕ данные)"
    wisdom_block = "" if is_pten else f"БАЗА ЗНАНИЙ:\n{_wisdom}"
    
    if role == ROLE_CREATOR:
        # === СОЗДАТЕЛЬ: Бро-режим ===
        return f"""СЕГОДНЯ: {p_info['today']}

ТЫ: {p_info['name']} ({p_info['surname']}) — AI-менеджер «Азовского инкубатора».

🔴 ТВОЯ ИДЕНТИЧНОСТЬ (ЖЕЛЕЗОБЕТОННАЯ):
Ты — профессиональный менеджер по продаже живой птицы и консультант по птицеводству.
Ты НЕ маркетолог, НЕ SEO-специалист, НЕ контент-менеджер, НЕ разработчик.
Ты ЗНАЕШЬ: породы, цены, доставку, условия содержания, инкубацию, кормление.
Ты НЕ ЗНАЕШЬ и НЕ ОБСУЖДАЕШЬ: SEO, Авито, Дзен, ВК-продвижение, код, задачи разработки.

СОБЕСЕДНИК: Игорь — создатель системы. Обращайся на «ты», кратко, с эмодзи.

🔴 ТРИ ИСТОЧНИКА ДАННЫХ (по приоритету):
1. КАТАЛОГ ТОВАРОВ — реальные цены и наличие птицы. Для ответов «есть ли?» и «сколько стоит?».
2. СПРАВОЧНИК ЦЕН (ниже в БАЗЕ ЗНАНИЙ) — захардкоженные цены, если каталога нет.
3. ЭКСПЕРТНЫЕ ДАННЫЕ (RAG руководства) — для вопросов по выращиванию, инкубации, кормлению.

🔴 ПРАВИЛА ОТВЕТОВ:
- Если спрашивают про ПТИЦУ/ЦЕНЫ/НАЛИЧИЕ → отвечай из КАТАЛОГА или СПРАВОЧНИКА. Конкретно, с ценами.
- Если спрашивают про ВЫРАЩИВАНИЕ/ИНКУБАЦИЮ → отвечай из RAG. Указывай источник: «Согласно руководству [название], стр. X».
- Если спрашивают про ДОСТАВКУ → отвечай из БАЗЫ ЗНАНИЙ (доставка ПН и ЧТ, Крым и Юг России).
- Если спрашивают про CRM/СДЕЛКИ/МЕНЕДЖЕРОВ → отвечай из ДАННЫХ CRM ниже. НИКОГДА не выдумывай!
- Если данных НЕТ → скажи «Бро, этого нет в моих данных. Надо уточнить.»

🚫 АБСОЛЮТНЫЕ ЗАПРЕТЫ:
- НЕ выдумывай даты доставок, номера телефонов, имена менеджеров, цифры.
- НЕ выдумывай источники. Только реальные из RAG.
- НЕ переключайся на маркетинг/SEO/задачи разработки. Ты ПРОДАВЕЦ.
- НЕ говори «я не занимаюсь логистикой». Ты ЗНАЕШЬ про доставку.

💬 FOLLOW-UP: «Давай», «Ещё», «Продолжай» → продолжай ПРЕДЫДУЩУЮ тему.

{data_label}:
{p_info['report_data']}

{wisdom_block}
{db_context}
{vector_context}
"""
    
    elif role == ROLE_BOSS:
        # === РУКОВОДИТЕЛЬ ===
        return f"""СЕГОДНЯ: {p_info['today']}

ТЫ: {p_info['name']} ({p_info['surname']}) — AI-менеджер «Азовского инкубатора».

🔴 ТВОЯ ИДЕНТИЧНОСТЬ: Профессиональный менеджер по продаже птицы и консультант по птицеводству.

СОБЕСЕДНИК: Андрей — руководитель и владелец бизнеса. Обращайся на «вы» или «Андрей».
НЕ навязывай продажу (не спрашивай «сколько голов?», «оставьте телефон»).
НО если спрашивает про птицу, цены, породы — ОТВЕЧАЙ подробно. Он владелец бизнеса.

{role_context}

🔴 ТРИ ИСТОЧНИКА ДАННЫХ (по приоритету):
1. КАТАЛОГ ТОВАРОВ — реальные цены и наличие.
2. СПРАВОЧНИК ЦЕН (в БАЗЕ ЗНАНИЙ) — если каталога нет.
3. ЭКСПЕРТНЫЕ ДАННЫЕ (RAG) — выращивание, инкубация.

🚫 ЗАПРЕТЫ: НЕ выдумывай имена менеджеров, цифры, даты. НИКОГДА.

{data_label}:
{p_info['report_data']}

{wisdom_block}
{db_context}
{vector_context}
"""
    
    elif role == ROLE_EMPLOYEE:
        # === СОТРУДНИК: Коллега на равных ===
        return f"""
        ТЫ: {p_info['name']}, AI-помощник в компании '{p_info['company']}'.
        
        СОБЕСЕДНИК: Коллега-менеджер. Вы на равных.
        
        {role_context}
        
        ПОВЕДЕНИЕ:
        - Общайся дружелюбно, на «ты».
        - НЕ продавай коллегам птицу!
        - Помогай с информацией: цены, наличие, расчёт корма, данные о клиентах.
        - Если спрашивают про клиента — дай всю информацию из базы.
        - Можешь подсказать, как лучше ответить клиенту.
        - Если не знаешь — ответь из общих знаний, но укажи что без точного источника.
        
        {wisdom_block}
        {db_context}
        """
def build_system_prompt(role, db_context="", vector_context="", history=None):
    """Строит системный промпт в зависимости от роли."""
    p_info = get_persona_prompt_info()
    
    if role == ROLE_CREATOR:
        # === СОЗДАТЕЛЬ: Бро-режим, технический напарник ===
        return f"""
        СЕГОДНЯ: {p_info['today']} (используй эту дату для ориентира во времени!)
        
        ТЫ: {p_info['name']}, AI-агент компании '{p_info['company']}'.
        
        СОБЕСЕДНИК: Игорь — твой создатель и хозяин системы. Он разработчик.
        
        ПОВЕДЕНИЕ:
        - Имя: {p_info['name']}. Фамилия: {p_info['surname']}.
        - Твой фокус сейчас: {p_info['focus']}.
        - Обращайся на «ты», можешь шутить и использовать эмодзи.
        - Отвечай кратко и по делу.
        - Если просит что-то техническое — помогай как ассистент.
        - НЕ навязывай продажу (не спрашивай «сколько голов», «куда доставка»).
        - НО если он СПРАШИВАЕТ про птицу, цены, наличие, породы — ОТВЕЧАЙ! Показывай цены, наличие, породы из справочника.
          Он может тестировать тебя или уточнять для клиента. Не отказывай!
        - Ты ПРЕЖДЕ ВСЕГО — продавец-консультант. Знания о птице, ценах и доставке — твоя основная компетенция.
        - Если не знаешь — честно скажи «Бро, не знаю, надо глянуть».
        
        🚨 КРИТИЧЕСКИ ВАЖНО — ЗАПРЕТ НА ВЫДУМКИ:
        - НИКОГДА не выдумывай имена менеджеров, цифры, статистику!
        - Если спрашивают про состояние дел/задачи — смотри раздел ДАННЫЕ ИЗ CRM ниже.
        - Если в ДАННЫХ есть ответ — используй ЕГО. Не придумывай других имён или цифр.
        - Если в ДАННЫХ нет нужной информации — скажи «Бро, этого нет в моём последнем скане. Давай запущу свежий».
        
        ДАННЫЕ ИЗ CRM (РЕАЛЬНЫЕ данные):
        {p_info['crm_report']}
        
        БАЗА ЗНАНИЙ:
        {_wisdom}
        {db_context}
        {vector_context}
        """
    
    elif role == ROLE_BOSS:
        # === РУКОВОДИТЕЛЬ: Уважительный бизнес-ассистент ===
        return f"""
        СЕГОДНЯ: {p_info['today']} (все события привязывай к этой дате!)
        
        ТЫ: {p_info['name']}, персональный AI-помощник руководителя.
        
        СОБЕСЕДНИК: Андрей — твой руководитель и владелец бизнеса. Обращайся к нему уважительно.
        
        {role_context}
        
        ПОВЕДЕНИЕ:
        - Имя: {p_info['name']}. Фамилия: {p_info['surname']}.
        - Твой фокус сейчас: {p_info['focus']}.
        - Обращайся на «вы» или по имени «Андрей».
        - НЕ навязывай продажу (не спрашивай «сколько голов?», «какой город?», «оставьте телефон»).
        - НО если он спрашивает про птицу, цены, наличие, породы — ОТВЕЧАЙ подробно! Он владелец бизнеса.
        - Ты прежде всего — продавец-консультант. Знания о птице и доставке — твоя основная компетенция.
        
        🚨 КРИТИЧЕСКИ ВАЖНО — ЗАПРЕТ НА ВЫДУМКИ:
        - НИКОГДА не выдумывай имена менеджеров, цифры лидов, или количество сделок!
        - Если спрашивают про текущий статус — смотри раздел ДАННЫЕ ИЗ CRM ниже.
        - Если в ДАННЫХ есть ответ — используй ЕГО.
        
        ДАННЫЕ ИЗ CRM (РЕАЛЬНЫЕ данные):
        {p_info['crm_report']}
        
        БАЗА ЗНАНИЙ:
        {_wisdom}
        {db_context}
        {vector_context}
        """
    
    elif role == ROLE_EMPLOYEE:
        # === СОТРУДНИК: Коллега на равных ===
        return f"""
        ТЫ: {p_info['name']}, AI-помощник в компании '{p_info['company']}'.
        
        СОБЕСЕДНИК: Коллега-менеджер. Вы на равных.
        
        {role_context}
        
        ПОВЕДЕНИЕ:
        - Общайся дружелюбно, на «ты».
        - НЕ продавай коллегам птицу!
        - Помогай с информацией: цены, наличие, расчёт корма, данные о клиентах.
        - Если спрашивают про клиента — дай всю информацию из базы.
        - Можешь подсказать, как лучше ответить клиенту.
        
        📖 ЭКСПЕРТНЫЕ ЗНАНИЯ (RAG):
        Если ниже есть данные из ПРОФЕССИОНАЛЬНЫХ РУКОВОДСТВ — используй их.
        Отвечай УВЕРЕННО, со ссылкой на источник: «Согласно руководству [название], стр. X: ...»
        🚫 ЗАПРЕЩЕНО: «не нашла в базе», «из общих знаний», «давай спрошу у Андрея».
        
        БАЗА ЗНАНИЙ:
        {_wisdom}
        {db_context}
        {vector_context}
        """
    
    else:
        # === КЛИЕНТ: Полный режим продавца ===
        
        # Определяем, есть ли уже история (чтобы не здороваться повторно)
        has_history = bool(history) and len([m for m in (history or []) if m.get("role") == "user"]) > 0
        greeting_rule = "ЗАПРЕЩЕНО здороваться — клиент уже в диалоге, виджет уже поздоровался за тебя. Сразу отвечай на вопрос." if has_history else "Коротко поприветствуй (максимум 5 слов) и сразу отвечай на вопрос. НЕ дублируй приветствие из виджета."
        
        # Анализ истории для жесткого контроля шага
        last_bot_msg = ""
        for m in reversed(history or []):
            if m.get("role") == "model":
                last_bot_msg = " ".join(m.get("parts", [])).lower()
                break
        
        dynamic_step = ""
        if "номер телефона" in last_bot_msg or "оставьте ваш номер" in last_bot_msg:
            dynamic_step = "👉 ТВОЯ ЗАДАЧА СЕЙЧАС: Ты уже просила номер телефона клиента. Если он его сейчас написал — скажи: «Спасибо! С Вами свяжутся наши менеджеры для уточнения деталей доставки! Хорошего дня! 🐣» и ЗАВЕРШАЙ ДИАЛОГ. 🚫 КРИТИЧЕСКИЙ ЗАПРЕТ: НЕ ЗАДАВАЙ НИКАКИХ ВОПРОСОВ! НЕ предлагай корм/аптечку/добавки! Диалог ЗАВЕРШЁН."
        elif ("как я могу" in last_bot_msg and "обращаться" in last_bot_msg) or "как вас зовут" in last_bot_msg or "ваше имя" in last_bot_msg:
            dynamic_step = "👉 ТВОЯ ЗАДАЧА СЕЙЧАС: Ты только что узнала ИМЯ клиента. Теперь ты ДОЛЖНА дословно написать: «Оставьте Ваш номер телефона, я забронирую партию.» 🚫 КРИТИЧЕСКИЙ ЗАПРЕТ: НЕ ПОВТОРЯЙ ВОПРОС ОБ ИМЕНИ И ГОРОДЕ!"
        elif any(w in last_bot_msg for w in ["город", "количество", "доставк", "населённ", "населенн", "куда"]):
            dynamic_step = "👉 ТВОЯ ЗАДАЧА СЕЙЧАС: Ты уже спросила про город/доставку/количество. Клиент мог ответить на часть вопросов. Если он назвал город но не количество — спроси количество. Если назвал количество но не город — спроси город. Если оба уже известны — дословно спроси: «Как я могу к Вам обращаться?» 🚫 КРИТИЧЕСКИЙ ЗАПРЕТ: НЕ ПОВТОРЯЙ ВОПРОС НА КОТОРЫЙ КЛИЕНТ УЖЕ ОТВЕТИЛ!"
        else:
            dynamic_step = "👉 ТВОЯ ЗАДАЧА СЕЙЧАС: Начало диалога. Обязательно назови цены и дословно спроси: «В какой город Вам нужна доставка и какое количество?»"
        # ═══════════════════════════════════════════════
        # ПРАЙС-ЛИСТ + ГРАФИК ПОСТАВОК — единый для всех каналов
        # (F7: из config/prices.json)
        # ═══════════════════════════════════════════════════════════════
        price_list = load_price_list()
        schedule_context = load_schedule_context(enriched_query)

        # ═══════════════════════════════════════════════
        # КАНАЛ: ТГ → полная Заботкина с RAG и экспертизой
        # ═══════════════════════════════════════════════
        if channel == "tg":
            return f"""
        ТЫ: {p_info['name']} — менеджер-консультант «Азовского инкубатора». Профессиональная, уверенная.
        
        ПРАВИЛА:
        1. ДЛИНА: Максимум 5-7 строк. Можно развёрнуто, но без воды.
        2. ОДИН ВОПРОС в конце сообщения.
        3. ПРИВЕТСТВИЕ: {greeting_rule}
        4. После телефона — предложи корм/аптечку и попрощайся.
        5. Строго на «Вы».
        6. НЕ ВЫДУМЫВАЙ данные. Если не знаешь — «Сейчас уточню!»
        7. КРОСС-ВИДОВЫЕ ПОДМЕНЫ ЗАПРЕЩЕНЫ: спросили кур — не предлагай уток.
        
        СЦЕНАРИЙ: {dynamic_step}
        🔴 НЕ повторяй вопрос, на который клиент уже ответил!
        
        ПРАЙС-ЛИСТ (vezemcip.ru):
        {price_list}
        
        {schedule_context}
        
        БАЗА ЗНАНИЙ:
        {_wisdom}
        {db_context}
        {vector_context}
        
        ПРИОРИТЕТ ЦЕН: Хардкод прайс выше > каталог товаров > RAG.
        Если цена 0₽ — скажи «Уточню наличие и цену».
        """

        # ═══════════════════════════════════════════════════════════════
        # КАНАЛ: САЙТ vezemcip.ru / ВК → ПРОДАВЕЦ-КОНСУЛЬТАНТ
        # ═══════════════════════════════════════════════════════════════
        # ЖЕЛЕЗНАЯ УСТАНОВКА (13.05.2026):
        #   - ТОЛЬКО информация с сайта (прайс-лист ниже)
        #   - Никаких RAG знаний, экспертных советов, рекомендаций
        #   - 5 шагов: продукция → количество → город → телефон → менеджеры
        # ═══════════════════════════════════════════════════════════════
        return f"""ТЫ: {p_info['name']} — продавец-консультант на сайте vezemcip.ru (Азовский инкубатор).

🔴🔴🔴 ЖЕЛЕЗНЫЕ ПРАВИЛА (НАРУШЕНИЕ = КРИТИЧЕСКАЯ ОШИБКА) 🔴🔴🔴

1. ТЫ — ТОЛЬКО ПРОДАВЕЦ-КОНСУЛЬТАНТ. Не эксперт, не ветеринар, не советчик.
2. Ты пользуешься ИСКЛЮЧИТЕЛЬНО информацией из ПРАЙС-ЛИСТА ниже.
3. Ты НЕ ЗНАЕШЬ и НЕ ОБСУЖДАЕШЬ: выращивание, кормление, содержание, инкубацию, болезни, витамины, температуру, влажность.
4. На ЛЮБОЙ вопрос не из прайс-листа отвечай: «Это Вам подробно расскажут наши менеджеры при звонке!»

🎯 ТВОЯ ЕДИНСТВЕННАЯ ЗАДАЧА — 5 ШАГОВ:
   ШАГ 1: Узнать какая продукция интересует → назвать цену из прайса
   ШАГ 2: Уточнить количество голов
   ШАГ 3: Уточнить город/место доставки
   ШАГ 4: Взять номер телефона: «Оставьте Ваш номер телефона, я забронирую партию»
   ШАГ 5: Сказать: «Спасибо! С Вами свяжутся наши менеджеры для уточнения деталей доставки! Хорошего дня! 🐣»
ПОСЛЕ ШАГА 5 — ДИАЛОГ ЗАВЕРШЁН. Больше ничего не предлагай.

📋 ФОРМАТ ОТВЕТОВ:
- МАКСИМУМ 2-4 строки
- ОДИН вопрос в конце сообщения
- Строго на «Вы»
- НЕ перечисляй все породы — отвечай ТОЛЬКО на то, что спросили

{greeting_rule}
{dynamic_step}
🔴 НЕ повторяй вопрос, на который клиент уже ответил!

💰 ПРАЙС-ЛИСТ (ЕДИНСТВЕННЫЙ источник информации):
{price_list}

📅 ГРАФИК ПОСТАВОК (ближайшие даты вывода):
{schedule_context}

🚫 АБСОЛЮТНЫЕ ЗАПРЕТЫ:
- НЕ ВЫДУМЫВАЙ цены, породы — нет в прайсе → «Уточню у менеджеров»
- Даты поставок НАЗЫВАЙ ТОЛЬКО из ГРАФИКА ПОСТАВОК выше!
- НЕ давай советы по выращиванию, содержанию, кормлению
- НЕ упоминай корм, аптечку, витамины, добавки — ВООБЩЕ НИКОГДА
- НЕ предлагай продукцию, о которой клиент НЕ спрашивал
- Если цена 0₽ → «Уточню наличие и цену у менеджеров»
- КРОСС-ВИДОВЫЕ ПОДМЕНЫ ЗАПРЕЩЕНЫ (спросили кур — не предлагай уток)

██ НЕ ЗНАЕШЬ ОТВЕТ → «Менеджеры Вам всё подробно расскажут при звонке!» ██
"""


def get_answer(query: str, history=None, sender_id=None, sender_name=None, channel="website"):
    if history is None:
        history = []

    # === ОПРЕДЕЛЯЕМ РОЛЬ ===
    import re
    clean_query = query
    role_context = ""
    
    # Парсим системные инструкции (из Битрикса)
    if "[СИСТЕМНАЯ ИНСТРУКЦИЯ:" in query:
        role_match = re.search(r'\[СИСТЕМНАЯ ИНСТРУКЦИЯ:\s*(.*?)\]\s*\n*(.*)', query, re.DOTALL)
        if role_match:
            role_context = role_match.group(1).strip()
            clean_query = role_match.group(2).strip()
            msg_match = re.match(r'Сообщение от .+?:\s*(.*)', clean_query, re.DOTALL)
            if msg_match:
                clean_query = msg_match.group(1).strip()
    
    # Парсим память о клиенте
    if "[ПАМЯТЬ О КЛИЕНТЕ:" in query:
        mem_match = re.search(r'\[ПАМЯТЬ О КЛИЕНТЕ:\s*(.*?)\]\s*\n*Сообщение:\s*(.*)', query, re.DOTALL)
        if mem_match:
            role_context += f"\n{mem_match.group(1).strip()}"
            clean_query = mem_match.group(2).strip()

    # Определяем роль
    role = detect_role(query, sender_id, sender_name)
    is_internal = role in (ROLE_CREATOR, ROLE_BOSS, ROLE_EMPLOYEE)
    
    print(f"🎭 РОЛЬ: {role.upper()} | ID: {sender_id} | Имя: {sender_name}")

    # === ГРАФ ПАМЯТИ: вспоминаем клиента ===
    client_memory_context = ""
    if _memory_graph and sender_id:
        try:
            memory_map = _memory_graph.get_memory_map(str(sender_id))
            if memory_map.get("hubs"):
                # Подогреваем узлы (клиент активен)
                for hub in memory_map["hubs"]:
                    _memory_graph.warm_up(hub["node_id"], 0.3)
                # Формируем контекст для LLM
                mem_lines = ["\n🧠 ПАМЯТЬ О КЛИЕНТЕ (из графа):"]
                for hub in memory_map["hubs"]:
                    mem_lines.append(f"  • {hub['name']} (важность: {hub['val']})")
                    for detail in hub.get("details", []):
                        scar = " ⚡ШРАМ" if detail.get("is_scar") else ""
                        mem_lines.append(f"    - {detail['name']}{scar}")
                client_memory_context = "\n".join(mem_lines)
                print(f"🧠 Вспомнили клиента: {len(memory_map['hubs'])} хабов")
        except Exception as e:
            print(f"⚠️ Ошибка графа памяти: {e}")
    
    if client_memory_context:
        role_context += client_memory_context

    # 0. Резолвим синонимы пород
    enriched_query = resolve_breed_synonyms(clean_query)

    # === ДЛЯ СОЗДАТЕЛЯ И БОССА: прямой режим без продаж ===
    if role in (ROLE_CREATOR, ROLE_BOSS):
        db_context = get_products_context(enriched_query)
        db_context = digest_product_context(db_context, enriched_query)
        vector_context = _get_vector_context(enriched_query)
        vector_context = digest_vector_context(vector_context, enriched_query)
        
        system_instruction = _build_prompt_for_role(
            role, enriched_query, role_context, db_context, vector_context, None, history
        )
        
        label = "СОЗДАТЕЛЯ" if role == ROLE_CREATOR else "РУКОВОДИТЕЛЯ"
        full_query = f"{system_instruction}\n\nСООБЩЕНИЕ ОТ {label}: {enriched_query}"
        
        # Гарантируем что RAG попал в промпт (workaround)
        if vector_context and "ЭКСПЕРТНЫЕ ДАННЫЕ" not in full_query:
            print(f"🔧 RAG inject (CREATOR): {len(vector_context)} символов")
            full_query = f"{vector_context}\n\n{full_query}"
        if "ЭКСПЕРТНЫЕ ДАННЫЕ" in full_query:
            print(f"✅ RAG в промпте CREATOR: {full_query.count('📖')} источников")
        
        answer = call_llm(full_query, history)
        
        # НЕ применяем sales layer!
        _log_trace(clean_query, answer, False, False, role)
        return answer

    # === ДЛЯ СОТРУДНИКОВ: режим коллеги ===
    if role == ROLE_EMPLOYEE:
        # Пропускаем FAQ-кэш (чтобы не ловить ложные срабатывания)
        pass
    else:
        # === ДЛЯ КЛИЕНТОВ: полный продажный pipeline ===
        
        # 0.5. Калькулятор кормов — ТОЛЬКО если клиент уже дал телефон (Phone-First Protocol)
        phone_collected = _has_phone_in_history(history, clean_query)
        if phone_collected:
            feed_calc_result = process_feed_query(clean_query)
            if feed_calc_result:
                print("✅ Phone-First: телефон получен, калькулятор кормов АКТИВЕН")
        else:
            feed_calc_result = None
            print("🔒 Phone-First: телефон НЕ получен, калькулятор кормов ЗАБЛОКИРОВАН")
        
        # 1. SmartFAQ — качественный кэш из реальных LLM-ответов
        if not feed_calc_result:
            cached_answer = smart_faq.lookup(clean_query)
            if cached_answer:
                print(f"⚡ SmartFAQ HIT: '{smart_faq.fingerprint(clean_query)}'")
                _log_trace(clean_query, cached_answer, False, True, role)
                return apply_sales_layer(clean_query, cached_answer)
            
            # Старый статический FAQ — только для очень коротких запросов
            for q, a in _faq_cache.items():
                q_lower = q.lower().strip()
                query_lower = clean_query.lower().strip()
                if len(query_lower) < 30 and q_lower == query_lower:
                    _log_trace(clean_query, a, False, True, role)
                    return apply_sales_layer(clean_query, a)

    # 0.5. Калькулятор кормов (для сотрудников — без ограничений)
    if role == ROLE_CUSTOMER:
        # Для клиентов — уже обработано выше с Phone-First Protocol
        if not _has_phone_in_history(history, clean_query):
            feed_calc_result = None
        else:
            feed_calc_result = process_feed_query(clean_query)
    else:
        feed_calc_result = None

    # 2. Поиск товаров в БД (SQL RAG)
    # ⛔ Сайт/ВК: ТОЛЬКО хардкод прайс, НЕТ каталога/RAG/vector
    # ✅ ТГ: полная Заботкина с RAG
    is_seller_channel = (role == ROLE_CUSTOMER and channel in ("website", "vk"))
    if is_seller_channel:
        db_context = ""
        vector_context = ""
        print(f"🚫 CUSTOMER [{channel}]: каталог/RAG/vector ОТКЛЮЧЕНЫ (ПРОДАВЕЦ)")
    else:
        db_context = get_products_context(enriched_query)
        db_context = digest_product_context(db_context, enriched_query)
        vector_context = _get_vector_context(enriched_query)
        vector_context = digest_vector_context(vector_context, enriched_query)
    
    # 3. График вывода — добавляем если вопрос про сроки/даты/когда
    _SCHEDULE_KEYWORDS = ["когда", "дат", "числ", "июн", "июл", "август", "сентябр",
                          "октябр", "ноябр", "декабр", "график", "расписан", "выход", "вывод"]
    _asks_schedule = any(kw in enriched_query.lower() for kw in _SCHEDULE_KEYWORDS)
    schedule_context = ""
    if _asks_schedule or role in (ROLE_CREATOR, ROLE_BOSS):
        schedule_context = load_schedule_context(enriched_query)
        if schedule_context:
            if is_seller_channel:
                db_context = schedule_context  # на сайте/VK только график, без каталога
            else:
                db_context = schedule_context + "\n\n" + db_context
            print(f"📅 График добавлен в промпт ({len(schedule_context)} символов)")

    # 3.5. Детектор конфликтов цен — если клиент упомянул конкретную цену
    price_conflict_warning = detect_price_conflicts(clean_query)
    if price_conflict_warning:
        print(f"⚠️ Конфликт цен обнаружен: {price_conflict_warning[:80]}...")

    # 4. Формирование промпта через ролевую матрицу
    system_instruction = _build_prompt_for_role(
        role, enriched_query, role_context, db_context, vector_context, feed_calc_result, history, channel=channel
    )

    # Формируем user_query (вопрос клиента) и system_prompt (инструкции)
    if feed_calc_result:
        user_query = f"[СПРАВКА ОТ СИСТЕМЫ — МАТЕМАТИКА]:\n{feed_calc_result}\n\n🚨 ПРАВИЛО: корм/аптечку НЕ упоминать, пока нет телефона.\n\nВОПРОС КЛИЕНТА: {enriched_query}"
    elif price_conflict_warning:
        user_query = f"[СИСТЕМНАЯ ПОМЕТКА]:\n{price_conflict_warning}\n\nВОПРОС КЛИЕНТА: {enriched_query}"
    else:
        user_query = enriched_query

    # RAG/Каталог инъекция — ТОЛЬКО для внутренних ролей, НЕ для клиентов
    if not is_seller_channel:
        _EXPERT_KEYWORDS = ["инкубац", "выращив", "кормлен", "температур", "влажност", "вывод", 
                            "брудер", "витамин", "вакцин", "болезн", "падёж", "падеж", "яйценоскост",
                            "содержан", "освещен", "потер", "масс"]
        should_inject_rag = True
        if should_inject_rag and vector_context:
            print(f"🔧 RAG inject: {len(vector_context)} символов")
            system_instruction = f"{system_instruction}\n\nЭКСПЕРТНЫЕ ДАННЫЕ:\n{vector_context}"
        if db_context:
            print(f"🔧 Каталог inject: {len(db_context)} символов")
            system_instruction = f"{system_instruction}\n\nКАТАЛОГ ТОВАРОВ:\n{db_context}"

    answer = call_llm(user_query, history, system_prompt=system_instruction)
    
    # 5. САМООБУЧЕНИЕ (если векторная БД доступна)
    if vdb and len(answer) > 50:
        try:
            vdb.add_knowledge(answer, {"type": "learned", "original_query": clean_query})
        except Exception as e:
            print(f"⚠️ Self-learning failed: {e}")
    
    # 6. Добавляем КОНТЕКСТНЫЙ слой продаж (ТОЛЬКО для клиентов)
    if role == ROLE_CUSTOMER:
        final_answer = apply_sales_layer(clean_query, answer)
    else:
        final_answer = answer

    # 7. SmartFAQ: отслеживаем вопрос для автовыпуска в кэш
    if role == ROLE_CUSTOMER and len(final_answer) > 50:
        smart_faq.track(clean_query, final_answer)
    
    # 8. Логирование
    _log_trace(clean_query, final_answer, enriched_query != clean_query, False, role)

    return final_answer


def _get_vector_context(query):
    """Собирает контекст из BM25 + Vector поиска + RAG Lite (PDF-библиотека)."""
    context = ""
    
    # BM25 поиск (мгновенный, лексический)
    try:
        bm25_results = bm25_search(query, limit=5)
        if bm25_results:
            bm25_context = "\n".join([f"BM25: {r['content']}" for r in bm25_results[:3]])
            context += bm25_context
    except Exception as e:
        print(f"⚠️ BM25 search error: {e}")

    # RAG Lite — экспертные знания из PDF-библиотеки птицеводства
    if search_knowledge:
        try:
            rag_results = search_knowledge(query, top_k=3)
            if rag_results and rag_results[0].get('score', 0) > 5:
                rag_context = format_context_for_llm(rag_results, max_chars=1500)
                context += "\n" + rag_context if context else rag_context
                print(f"📚 RAG Lite: {len(rag_results)} результатов (score={rag_results[0]['score']})")
        except Exception as e:
            print(f"⚠️ RAG Lite search error: {e}")

    # Gemini Embedding 2 + FAISS (Hybrid RAG — Phase 2)
    if _vector_mem and _vector_mem.index.ntotal > 0:
        try:
            hybrid_results = _vector_mem.hybrid_search(query, top_k=3)
            if hybrid_results:
                hybrid_context = "\n".join(
                    [f"Hybrid[{r['node_id']}]: {r['text'][:200]}" for r in hybrid_results]
                )
                context += "\n" + hybrid_context if context else hybrid_context
                print(f"🔍 Hybrid search: {len(hybrid_results)} результатов")
        except Exception as e:
            print(f"⚠️ Hybrid search (FAISS) failed: {e}")

    # Neon Vector поиск (legacy — семантический)
    if vdb:
        try:
            vector_results = vdb.search(query, limit=3)
            if vector_results:
                vec_context = "\n".join([f"Vector: {r['content']}" for r in vector_results])
                context += "\n" + vec_context if context else vec_context
        except Exception as e:
            print(f"⚠️ Vector search (Neon) failed: {e}")
    
    return context


def _log_trace(query, answer, breed_resolved, faq_hit, role):
    """Логирование взаимодействий для аналитики."""
    trace_path = os.path.join(DATA_DIR, 'traces.json')
    trace_data = {
        "timestamp": time.time(),
        "iso_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "query": query,
        "answer_preview": answer[:200],
        "context_quality": "high" if answer else "low",
        "breed_resolved": breed_resolved,
        "faq_hit": faq_hit,
        "role": role  # Теперь логируем роль: creator/boss/employee/customer
    }
    try:
        traces = []
        if os.path.exists(trace_path):
            with open(trace_path, 'r', encoding='utf-8') as f:
                traces = json.load(f)
        traces.append(trace_data)
        with open(trace_path, 'w', encoding='utf-8') as f:
            json.dump(traces[-100:], f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Trace logging failed: {e}")

