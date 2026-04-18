import os
import json
import time
import requests
from sales_logic import apply_sales_layer, resolve_breed_synonyms
from feed_calculator import process_feed_query
from hybrid_search import bm25_search, hybrid_search, init_bm25_index

# Загружаем настройки
from dotenv import load_dotenv

# Определяем базовую директорию проекта (абсолютный путь)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

load_dotenv(override=True)

# Если ключей нет локально, пробуем найти их в родительской папке
if not os.getenv("GEMINI_API_KEY"):
    load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
NEON_DATABASE_URL = os.getenv("NEON_DATABASE_URL")

# --- Каскадный LLM-движок ---
# Приоритет 1: Gemini напрямую (требует US-прокси)
# Приоритет 2: OpenRouter (работает без прокси)
# Приоритет 3: Ollama/Gemma4 локально (оффлайн-страховка)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e2b")

def _call_gemini_direct(prompt, history=None):
    """Вызов Gemini API напрямую (требует прокси для РФ)"""
    if not GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")
        chat = model.start_chat(history=history or [])
        response = chat.send_message(prompt)
        return response.text
    except Exception as e:
        print(f"⚠️ Gemini Direct failed: {e}")
        return None

def _call_openrouter(prompt, history=None):
    """Вызов через OpenRouter (работает из любого региона)"""
    if not OPENROUTER_KEY:
        return None
    
    messages = []
    # Конвертируем историю Gemini-формата в OpenAI-формат
    if history:
        for msg in history:
            role = "assistant" if msg.get("role") == "model" else msg.get("role", "user")
            content = msg.get("parts", [msg.get("content", "")])[0] if isinstance(msg.get("parts"), list) else msg.get("content", "")
            messages.append({"role": role, "content": content})
    
    messages.append({"role": "user", "content": prompt})
    
    # Каскад моделей OpenRouter
    or_models = [
        "google/gemini-2.0-flash-001",
        "google/gemini-2.0-flash-exp:free",
        "meta-llama/llama-3.1-8b-instruct:free",
    ]
    
    for model_name in or_models:
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
                json={"model": model_name, "messages": messages},
                timeout=20
            )
            data = resp.json()
            if "choices" in data:
                return data["choices"][0]["message"]["content"]
            else:
                print(f"⚠️ OpenRouter {model_name}: {data.get('error', 'Unknown error')}")
        except Exception as e:
            print(f"⚠️ OpenRouter {model_name} exception: {e}")
    
    return None

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
        print(f"⚠️ Ollama не запущена (http://localhost:11434 недоступен)")
        return None
    except Exception as e:
        print(f"⚠️ Ollama/{OLLAMA_MODEL} failed: {e}")
        return None

def call_llm(prompt, history=None):
    """Каскадный вызов: OpenRouter → Gemini Direct → Ollama/Gemma4 (offline)"""
    # Шаг 1: OpenRouter (основной — Gemini через API, квота стабильна)
    result = _call_openrouter(prompt, history)
    if result:
        return result
    
    # Шаг 2: Gemini Direct (бэкап, free-tier квота может быть исчерпана)
    result = _call_gemini_direct(prompt, history)
    if result:
        return result
    
    # Шаг 3: Оффлайн-страховка — Gemma4 через Ollama
    print("🔌 Облачные модели недоступны. Переключаюсь на Gemma4 (оффлайн)...")
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

# Загружаем последний скан Битрикс24 (реальные данные о менеджерах/сделках)
_crm_report = ""
_crm_report_path = os.path.join(DATA_DIR, 'latest_scan_report.md')
if os.path.exists(_crm_report_path):
    with open(_crm_report_path, 'r', encoding='utf-8') as f:
        _crm_report = f.read()
    print(f"✅ CRM отчёт загружен: {len(_crm_report)} символов")

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


# --- RAG: поиск товаров напрямую из SQL (без эмбеддингов) ---
def get_products_context(query):
    """Поиск товаров в БД по ключевым словам"""
    if not NEON_DATABASE_URL:
        return ""
    try:
        import psycopg2
        import re
        q = query.lower()
        clean = re.sub(r'[^\w\s]', '', q)
        words = [w for w in clean.split() if len(w) > 2]
        if not words:
            return ""
        
        conn = psycopg2.connect(NEON_DATABASE_URL)
        cur = conn.cursor()
        results = []
        for word in words[:5]:  # Ограничиваем количество запросов
            cur.execute(
                "SELECT name, price, stock_status FROM products WHERE name ILIKE %s OR description ILIKE %s LIMIT 5",
                (f"%{word}%", f"%{word}%")
            )
            results.extend(cur.fetchall())
        cur.close()
        conn.close()
        
        if results:
            seen = set()
            items = []
            for r in results:
                if r[0] not in seen:
                    items.append(f"- {r[0]}: {r[1]} руб. ({r[2]})")
                    seen.add(r[0])
            return "\n\nТОВАРЫ ИЗ БАЗЫ ДАННЫХ:\n" + "\n".join(items)
        return ""
    except Exception as e:
        print(f"⚠️ DB search error: {e}")
        return ""


# === РОЛЕВАЯ МАТРИЦА ===
# 4 роли с ПОЛНОСТЬЮ разным поведением
ROLE_CREATOR = "creator"     # Игорь — создатель/хозяин системы  
ROLE_BOSS = "boss"           # Андрей — руководитель бизнеса
ROLE_EMPLOYEE = "employee"   # Менеджеры — сотрудники на равных
ROLE_CUSTOMER = "customer"   # Покупатели — режим продавца

# ID создателя (Telegram)
CREATOR_TG_ID = "176203333"

# Известные имена руководителей (Битрикс)
BOSS_NAMES = ["андрей", "крымский хан", "руководитель", "владелец", "директор"]

# Известные имена менеджеров (Битрикс)
EMPLOYEE_NAMES = ["валя", "валентина", "менеджер", "оператор", "диспетчер"]


def detect_role(query: str, sender_id: str = None, sender_name: str = None):
    """Определяет роль собеседника по ID, имени и контексту сообщения."""
    import re
    
    # 1. Проверка по Telegram ID (самый надёжный)
    if sender_id and str(sender_id) == CREATOR_TG_ID:
        return ROLE_CREATOR
    
    # 2. Проверка из [СИСТЕМНАЯ ИНСТРУКЦИЯ:] (Битрикс)
    if "[СИСТЕМНАЯ ИНСТРУКЦИЯ:" in query:
        upper = query.upper()
        if "РУКОВОДИТЕЛ" in upper or "ВЛАДЕЛЕЦ" in upper or "ДИРЕКТОР" in upper:
            return ROLE_BOSS
        if "СОТРУДНИК" in upper or "МЕНЕДЖЕР" in upper:
            return ROLE_EMPLOYEE
        # Любая системная инструкция = внутренний пользователь
        return ROLE_EMPLOYEE
    
    # 3. Проверка по имени отправителя
    if sender_name:
        name_lower = sender_name.lower()
        for boss_name in BOSS_NAMES:
            if boss_name in name_lower:
                return ROLE_BOSS
        for emp_name in EMPLOYEE_NAMES:
            if emp_name in name_lower:
                return ROLE_EMPLOYEE
    
    # 4. По умолчанию — клиент
    return ROLE_CUSTOMER


def _build_prompt_for_role(role, query, role_context, db_context, vector_context, feed_calc_result):
    """Строит системный промпт в зависимости от роли."""
    
    if role == ROLE_CREATOR:
        # === СОЗДАТЕЛЬ: Бро-режим, технический напарник ===
        return f"""
        ТЫ: Анжелочка, AI-агент компании 'Азовский инкубатор'.
        
        СОБЕСЕДНИК: Игорь — твой создатель и хозяин системы. Он разработчик.
        
        ПОВЕДЕНИЕ:
        - Обращайся на «ты», можешь шутить и использовать эмодзи.
        - Отвечай кратко и по делу.
        - Если просит что-то техническое — помогай как ассистент.
        - НИКОГДА не продавай ему птицу и не спрашивай «сколько голов».
        - Если не знаешь — честно скажи «Бро, не знаю, надо глянуть».
        
        🚨 КРИТИЧЕСКИ ВАЖНО — ЗАПРЕТ НА ВЫДУМКИ:
        - НИКОГДА не выдумывай имена менеджеров, цифры, статистику!
        - Если спрашивают про менеджеров/звонки/сделки — смотри раздел ДАННЫЕ ИЗ CRM ниже.
        - Если в CRM ДАННЫХ есть ответ — используй ЕГО. Не придумывай других имён или цифр.
        - Если в CRM ДАННЫХ нет нужной информации — скажи «Бро, этого нет в моём последнем скане. Давай запущу свежий».
        - НИКОГДА не дополняй реальные данные выдуманными.
        
        ДАННЫЕ ИЗ CRM (ПОСЛЕДНИЙ СКАН БИТРИКС24 — это РЕАЛЬНЫЕ данные):
        {_crm_report}
        
        БАЗА ЗНАНИЙ:
        {_wisdom}
        {db_context}
        {vector_context}
        """
    
    elif role == ROLE_BOSS:
        # === РУКОВОДИТЕЛЬ: Уважительный бизнес-ассистент ===
        return f"""
        ТЫ: Анжелочка, персональный AI-помощник руководителя 'Азовского инкубатора'.
        
        СОБЕСЕДНИК: Андрей — руководитель и владелец бизнеса. Обращайся к нему уважительно.
        
        {role_context}
        
        ПОВЕДЕНИЕ:
        - Обращайся на «вы» или по имени «Андрей».
        - КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО продавать ему! Он БОСС, не клиент.
        - Никогда не спрашивай «сколько голов?», «какой город?», «оставьте телефон».
        - Если он спрашивает про цены/породы — ответь по делу и уточни: «Это для клиента?»
        - Если не знаешь информацию — скажи «Сейчас уточню и вернусь с ответом».
        
        🚨 КРИТИЧЕСКИ ВАЖНО — ЗАПРЕТ НА ВЫДУМКИ:
        - НИКОГДА не выдумывай имена менеджеров, цифры лидов, количество звонков или сделок!
        - Если спрашивают про менеджеров/звонки/сделки — смотри раздел ДАННЫЕ ИЗ CRM ниже.
        - Если в CRM ДАННЫХ есть ответ — используй ЕГО. Не придумывай других имён или цифр.
        - Если в CRM ДАННЫХ нет нужной информации — скажи «Андрей, этих данных нет в моём последнем скане. Могу запустить свежий».
        - НИКОГДА не дополняй реальные данные выдуманными.
        
        ФОРМАТ ОТВЕТОВ ДЛЯ РУКОВОДИТЕЛЯ:
        - Краткие, структурированные ответы
        - ТОЛЬКО реальные данные из CRM, без выдумок
        - Если данных нет — честно скажи
        
        ДАННЫЕ ИЗ CRM (ПОСЛЕДНИЙ СКАН БИТРИКС24 — это РЕАЛЬНЫЕ данные):
        {_crm_report}
        
        БАЗА ЗНАНИЙ:
        {_wisdom}
        {db_context}
        {vector_context}
        """
    
    elif role == ROLE_EMPLOYEE:
        # === СОТРУДНИК: Коллега на равных ===
        return f"""
        ТЫ: Анжелочка, AI-помощник в компании 'Азовский инкубатор'.
        
        СОБЕСЕДНИК: Коллега-менеджер. Вы на равных.
        
        {role_context}
        
        ПОВЕДЕНИЕ:
        - Общайся дружелюбно, на «ты».
        - НЕ продавай коллегам птицу!
        - Помогай с информацией: цены, наличие, расчёт корма, данные о клиентах.
        - Если спрашивают про клиента — дай всю информацию из базы.
        - Можешь подсказать, как лучше ответить клиенту.
        - Если не знаешь — скажи «Хм, не нашла. Давай спрошу у Андрея?»
        
        БАЗА ЗНАНИЙ:
        {_wisdom}
        {db_context}
        {vector_context}
        """
    
    else:
        # === КЛИЕНТ: Полный режим продавца ===
        return f"""
        ТЫ: Анжелочка, живая и прагматичная менеджер-хозяйка 'Азовского инкубатора'.
        
        ИНСТРУКЦИЯ ПО ПРОДАЖАМ:
        {_skill_instructions}
        
        ПРАВИЛА ОБЩЕНИЯ:
        1. ПРИВЕТСТВИЕ: Здоровайся ТОЛЬКО если это начало диалога. Если диалог уже идёт (есть история), сразу отвечай на вопрос.
        2. ЦЕЛЬ: Твоя главная задача — получить НОМЕР ТЕЛЕФОНА клиента для бронирования.
        3. КОРОТКИЕ ОТВЕТЫ: Если клиент пишет просто цифру (например, "124"), это значит он отвечает на твой вопрос о количестве. Подхватывай это!
        4. ZERO-CLICK: Давай полный ответ прямо в чате, не отправляй на сайт.
        5. КРОСС-СЕЙЛ: При вопросе о яйцах/птенцах — предложи корм. При вопросе о корме — уточни породу.
        6. ОГРАНИЧЕНИЕ ПО ДОСТАВКЕ: Подросшую птицу (сейчас это Доминанты — им ~1 неделя) КАТЕГОРИЧЕСКИ НЕ везем на дальние рейсы (например, в Воронеж или Краснодарский край). Они не доедут живыми. Отказывай в доставке Доминантов на дальние расстояния (предлагай только забрать по месту или только суточных бройлеров)!
        7. 🔴 КАТЕГОРИЧЕСКИЙ ЗАПРЕТ: ЕСЛИ клиент спрашивает про "ЦЫПЛЯТ" ИЛИ "КУР" — НИ В КОЕМ СЛУЧАЕ НЕ ПРЕДЛАГАЙ И НЕ УПОМИНАЙ УТОК, ГУСЕЙ ИЛИ ИНДЮКОВ! Отвечай СТРОГО только по курам/бройлерам.
        8. СТИЛЬ РЕЧИ: Избегай фамильярности вроде «у нас много кто есть» или «раз вы там-то». Пиши профессиональнее, например: «У нас есть в наличии...»
        
        БАЗА ЗНАНИЙ (УХОД ЗА ПТИЦЕЙ):
        {_wisdom}
        
        КАТАЛОГ ТОВАРОВ (ИЗ BITRIX24):
        {_product_catalog}
        
        ИНФОРМАЦИЯ О КОМПАНИИ:
        - Адрес самовывоза: Крым, Джанкойский район, пгт. Азовское, ул. Железнодорожная, 42.
        - Никакого самовывоза в Москве нет! Только Крым.
        - Доставка: ПН и ЧТ по Крыму и Югу России, специально оборудованный транспорт с климат-контролем.
        - Гарантия 100% выживаемости при доставке. Если что-то не так — замена или возврат денег на месте.
        - Оплата: наличные, перевод на карту или по реквизитам.
        - Минимальный заказ: бройлеры от 50 голов, утки от 20 голов, индюки от 10 голов, цветные бройлеры от 40 голов.
        
        🔴 ПРИОРИТЕТ ЦЕН: ВСЕГДА бери цену из БАЗЫ ЗНАНИЙ выше, а НЕ из каталога товаров. Если видишь расхождение — используй базу знаний.
        Ключевые цены: КОББ-500 = 90₽ (до 100 шт), РОСС-308 = 85₽ (до 100 шт). НИКОГДА не называй 60₽ за КОББ!
        
        CROSS-SELL: При заказе бройлеров — предложи комбикорм и аптечку (200₽). При заказе несушек — спроси нужны ли петухи (5₽/шт).
        ЗАМЕНА ПОРОД: Мастер Грей нет → Ред Бро. Биг-6 нет → Hybrid Converter. НИКОГДА не предлагай утку вместо кур!
        ТАРА: Напомни клиенту взять свои коробки для перевозки.
        
        {db_context}
        {vector_context}
        
        ВАЖНО: Говори кратко, по-человечески. Обращайся к клиентам СТРОГО НА «ВЫ». ЗАПРЕЩЕНО использовать «ты», «тебе», «тебя», «смотри», «глянь», «держи». Только «Вы», «Вам», «Вас», «обратите внимание», «посмотрите».
        СТРОГО ЗАПРЕЩЕНЫ уменьшительно-ласкательные слова (штучки, цыплятки, яички, секундочку). Пиши и говори только: штуки, цыплята, яйца, секунду.
        Не используй шаблоны "Добрый день" в каждой фразе. Никогда не говори "Я не знаю" — скажи "Сейчас уточню у наших птицеводов!".
        """


def get_answer(query: str, history=None, sender_id=None, sender_name=None):
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

    # 0. Резолвим синонимы пород
    enriched_query = resolve_breed_synonyms(clean_query)

    # === ДЛЯ СОЗДАТЕЛЯ И БОССА: прямой режим без продаж ===
    if role in (ROLE_CREATOR, ROLE_BOSS):
        db_context = get_products_context(enriched_query)
        vector_context = _get_vector_context(enriched_query)
        
        system_instruction = _build_prompt_for_role(
            role, enriched_query, role_context, db_context, vector_context, None
        )
        
        label = "СОЗДАТЕЛЯ" if role == ROLE_CREATOR else "РУКОВОДИТЕЛЯ"
        full_query = f"{system_instruction}\n\nСООБЩЕНИЕ ОТ {label}: {enriched_query}"
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
        
        # 0.5. Калькулятор кормов
        feed_calc_result = process_feed_query(clean_query)
        
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

    # 0.5. Калькулятор кормов (для всех)
    if role == ROLE_CUSTOMER:
        feed_calc_result = process_feed_query(clean_query)
    else:
        feed_calc_result = None

    # 2. Поиск товаров в БД (SQL RAG)
    db_context = get_products_context(enriched_query)
    
    # 3. Векторный поиск + BM25 гибрид
    vector_context = ""
    vector_results = []
    
    vector_context = _get_vector_context(enriched_query)
    
    # 4. Формирование промпта через ролевую матрицу
    system_instruction = _build_prompt_for_role(
        role, enriched_query, role_context, db_context, vector_context, feed_calc_result
    )
    
    # Если калькулятор сработал — добавляем результат в промпт
    if feed_calc_result:
        full_query = f"{system_instruction}\n\nРАСЧЁТ КАЛЬКУЛЯТОРА (используй эти данные в ответе, подай красиво):\n{feed_calc_result}\n\nВОПРОС КЛИЕНТА: {enriched_query}"
    else:
        full_query = f"{system_instruction}\n\nВОПРОС: {enriched_query}"
    answer = call_llm(full_query, history)
    
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
    """Собирает контекст из BM25 + Vector поиска."""
    context = ""
    
    # BM25 поиск (мгновенный, лексический)
    try:
        bm25_results = bm25_search(query, limit=5)
        if bm25_results:
            bm25_context = "\n".join([f"BM25: {r['content']}" for r in bm25_results[:3]])
            context += bm25_context
    except Exception as e:
        print(f"⚠️ BM25 search error: {e}")

    # Vector поиск (семантический)
    if vdb:
        try:
            vector_results = vdb.search(query, limit=3)
            if vector_results:
                vec_context = "\n".join([f"Vector: {r['content']}" for r in vector_results])
                context += "\n" + vec_context if context else vec_context
        except Exception as e:
            print(f"⚠️ Vector search failed: {e}")
    
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

