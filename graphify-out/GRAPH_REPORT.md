# Graph Report - agent  (2026-05-01)

## Corpus Check
- 116 files · ~63,838 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 932 nodes · 1356 edges · 53 communities detected
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 111 edges (avg confidence: 0.62)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]

## God Nodes (most connected - your core abstractions)
1. `MemoryGraph` - 29 edges
2. `VectorMemory` - 24 edges
3. `Avitolog` - 23 edges
4. `AngelochkaVectorDB` - 20 edges
5. `get_answer()` - 18 edges
6. `DryRunProvider` - 18 edges
7. `BitrixMCP` - 15 edges
8. `BitrixDiskManager` - 14 edges
9. `run_health_check()` - 13 edges
10. `NotifierHandler` - 13 edges

## Surprising Connections (you probably didn't know these)
- `run_proactive_cycle()` --calls--> `notify()`  [INFERRED]
  proactive_engine.py → a2a_protocol.py
- `run_proactive_cycle()` --calls--> `report_insight()`  [INFERRED]
  proactive_engine.py → a2a_protocol.py
- `ForcedIPResolver` --uses--> `Avitolog`  [INFERRED]
  tg_bot.py → avitolog.py
- `IPv4AiohttpSession` --uses--> `Avitolog`  [INFERRED]
  tg_bot.py → avitolog.py
- `Создаём aiogram-сессию. ФОРСИРУЕМ IPv4 и прямой IP.` --uses--> `Avitolog`  [INFERRED]
  tg_bot.py → avitolog.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.04
Nodes (48): Проверяет, оставил ли клиент телефон в истории диалога.     Phone-First Protocol, Умный FAQ: вопросы, которые задают 3+ раз, автоматически кэшируются     с КАЧЕСТ, Нормализует вопрос в 'отпечаток' для группировки похожих.         'Какие цыплята, Ищет ответ в кэше. Возвращает ответ или None., Отслеживает вопрос. Если задан 3+ раз — кэширует лучший ответ., Строит системный промпт в зависимости от роли., Определяет текущую личность Анжелы на основе окружения., Возвращает данные для системного промпта в зависимости от личности. (+40 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (62): AvitoAPI, Avitolog, log(), Получаем ВСЕ объявления с пагинацией., Статистика по объявлениям.                  API: POST /core/v1/items/stats, Детальная информация по объявлению.                  API: GET /core/v1/accounts/, Стоимость продвижения для объявлений.                  API: POST /core/v1/accoun, Главный агент-аудитор Авито. (+54 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (28): ABC, main(), normalize_phone(), NotifierHandler, Подставляет данные клиента в шаблон., Рассылает SMS всем клиентам.          Args:         clients: список клиентов из, Загрузка Excel-файла., Обновление шаблона SMS. (+20 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (26): chat(), ChatRequest, create_lead_endpoint(), _estimate_deal_amount(), LeadRequest, Оценивает сумму сделки из контекста диалога., Создаёт лид в Битрикс24 CRM из заявки на сайте., Чат с Анжелочкой. Поддерживает сессии для истории диалога. (+18 more)

### Community 4 - "Community 4"
Cohesion: 0.08
Nodes (29): AgentBus, AgentMessage, delegate_task(), from_dict(), notify(), Получает все сообщения для агента., Помечает сообщение как прочитанное., Помечает как выполненное с результатом. (+21 more)

### Community 5 - "Community 5"
Cohesion: 0.08
Nodes (34): get_dynamic_crm_report(), _auto_run_scanner(), build_report_text(), generate_ai_insights(), get_dynamic_crm_report(), get_dynamic_sandbox_report(), get_latest_sandbox_json(), get_latest_scan() (+26 more)

### Community 6 - "Community 6"
Cohesion: 0.09
Nodes (26): BitrixDiskManager, Находит Общий диск (common) или Личный диск пользователя., _acquire_lock(), approve_draft_callback(), cmd_avito_audit(), cmd_report(), cmd_restart(), cmd_silent() (+18 more)

### Community 7 - "Community 7"
Cohesion: 0.11
Nodes (34): _build_resurrect_cmd(), can_auto_heal(), check_all_pm2_processes(), check_heartbeat(), check_http_endpoints(), _check_pm2_process(), check_today_report(), do_auto_heal() (+26 more)

### Community 8 - "Community 8"
Cohesion: 0.09
Nodes (29): build_system_prompt(), _call_gemini_direct(), call_llm(), _call_ollama_local(), _call_openrouter(), get_answer(), get_current_persona(), get_persona_prompt_info() (+21 more)

### Community 9 - "Community 9"
Cohesion: 0.07
Nodes (18): run_full_beauty_cycle(), to_bbcode(), MarketerStrategist, Загружает скилл из базы знаний Antigravity, Генерирует ТЗ (бриф) для Шекспира (копирайтера) на заданную тему          с помо, 📈 Агент-Маркетолог (SEO/GEO/AEO)     Отвечает за сбор семантики, анализ видимост, Возвращает результат Птенчиковой или отправляет в песочницу Битрикс24, Создает промпт и "генерирует" изображение для статьи. (+10 more)

### Community 10 - "Community 10"
Cohesion: 0.16
Nodes (22): cmd_post(), cmd_post_all(), cmd_schedule(), cmd_status(), extract_poll_data(), load_posted_log(), main(), parse_posts_from_file() (+14 more)

### Community 11 - "Community 11"
Cohesion: 0.19
Nodes (22): acquire_lock(), log(), main(), now_msk(), Планировщик Анжелочки v3.0 — НАДЁЖНЫЙ. Замена cron. Работает как фоновый демон п, Запускает скрипт в subprocess с таймаутом., Запускает скрипт с повторами при неудаче., Задача: Вечерний аудит CRM. (+14 more)

### Community 12 - "Community 12"
Cohesion: 0.14
Nodes (10): PersistentHistory, Загрузить историю диалога из БД.                  Возвращает список в формате ai, Получить краткую сводку о клиенте из истории.                  Возвращает строку, Удалить старые записи (вызывать из scheduler)., Оставить только последние N сообщений для пользователя., Статистика БД для /status команды., Облачное хранилище истории диалогов в Neon PostgreSQL., Получить соединение с БД. (+2 more)

### Community 13 - "Community 13"
Cohesion: 0.16
Nodes (18): build_quality_report(), extract_summary(), get_all_calls(), get_calls_from_scan(), get_calls_from_transcripts(), get_manager_names(), Берём звонки из последнего скана CRM (activities → calls)., Берём звонки из транскрибированных файлов (shadow_learning). (+10 more)

### Community 14 - "Community 14"
Cohesion: 0.18
Nodes (17): bitrix_call(), check_dormant_clients(), check_forgotten_deals(), check_seasonal_opportunities(), generate_proactive_report(), log(), Находит клиентов, которые давно не обращались., Анализирует сезонный спрос и предлагает действия. (+9 more)

### Community 15 - "Community 15"
Cohesion: 0.16
Nodes (17): bitrix_api(), extract_summary(), format_call_entry(), get_manager_names(), is_bright(), iso_to_dt(), load_calls(), load_env() (+9 more)

### Community 16 - "Community 16"
Cohesion: 0.19
Nodes (16): bitrix_call(), bitrix_list_all(), Bitrix24 Scanner — «Тихий Наблюдатель» Анжелочки Сканирует новые сделки, звонки,, Активности: звонки, SMS, чаты, формы. Классификация по TYPE_ID + PROVIDER_ID., Товары и остатки (полный список)., Основной метод сканирования.          КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ (2026-05-01):, Вызов Bitrix24 REST API., Пагинация Bitrix (по 50 записей за раз). (+8 more)

### Community 17 - "Community 17"
Cohesion: 0.17
Nodes (15): fetch_hub_rss(), format_digest(), load_sent_links(), Habr Daily Digest -- ежедневный дайджест релевантных статей с Хабра.  Парсит RSS, Оценить релевантность статьи (0-100)., Загрузить уже отправленные ссылки., Сохранить отправленные ссылки (хранить последние 200)., Отправить сообщение в Telegram (обоим руководителям). (+7 more)

### Community 18 - "Community 18"
Cohesion: 0.18
Nodes (10): BM25, hybrid_search(), init_bm25_index(), Гибридный поиск: BM25 (лексический) + Vector (семантический). BM25 отлично ищет, Загружает данные из brain и строит BM25 индекс., Быстрый BM25 поиск по каталогу., BM25 лексический поиск по каталогу товаров., Простая токенизация: lowercase, удаление пунктуации. (+2 more)

### Community 19 - "Community 19"
Cohesion: 0.22
Nodes (13): approve_drafts(), deduplicate_drafts(), detect_conversion(), extract_successful_patterns(), load_json(), Авто-обучение Анжелочки на реальных диалогах. Анализирует логи: если клиент оста, Главный процесс обучения., Одобряет черновики и переносит в основной FAQ.     indices: список индексов для (+5 more)

### Community 20 - "Community 20"
Cohesion: 0.18
Nodes (6): ClientMemory, Возвращает текстовый контекст для промпта.                  Пример: 'Клиент Мари, Автоматически извлекает факты из диалога.                  Анализирует текст соо, Находит клиентов, не обращавшихся N дней., Personalized memory for each client., Сохраняет факт взаимодействия.                  interaction = {             "act

### Community 21 - "Community 21"
Cohesion: 0.31
Nodes (12): api(), collect_calls(), collect_leads(), collect_open_line_sessions(), extract_patterns(), log(), Собирает записи звонков., Собирает лиды с комментариями BitrixGPT. (+4 more)

### Community 22 - "Community 22"
Cohesion: 0.24
Nodes (11): daily_project_job(), daily_sales_job(), _load_modules(), morning_job(), Автопилот Анжелочки v3.0 — Планировщик двойных отчётов. ════════════════════════, 20:05 — ПТЕНЧИКОВА: Отчёт по продвижению IncuBird 2.0., Ленивая загрузка модулей отчётов., Отправить сообщение обоим руководителям. (+3 more)

### Community 23 - "Community 23"
Cohesion: 0.24
Nodes (11): get_active_tasks_summary(), get_sandbox_tasks(), get_today_chronicle(), get_vk_content_status(), Project Report — Ежедневный отчёт Анжелы Птенчиковой. Собирает РЕАЛЬНЫЕ данные и, Получает статус контента VK., Краткая сводка из ACTIVE_TASKS.md., Получает задачи из последнего скана Песочницы. (+3 more)

### Community 24 - "Community 24"
Cohesion: 0.27
Nodes (9): calculate_feed(), detect_feed_request(), get_bundle_info(), process_feed_query(), Калькулятор кормов и товарные наборы для Анжелочки. Автоматический расчёт: пород, Главная точка входа: определяет запрос и формирует ответ., Определяет, содержит ли запрос вопрос про корм/расчёт.     Возвращает {breed, co, Рассчитывает корм для указанного количества птицы. (+1 more)

### Community 25 - "Community 25"
Cohesion: 0.33
Nodes (8): main(), move_duplicates(), Calculate SHA‑256 hash of a file., Return dict {hash: [paths...]}. Only files are considered., For each hash with >1 files, keep the first (by sorted path) and move others., remove_empty_dirs(), scan_paths(), sha256_path()

### Community 26 - "Community 26"
Cohesion: 0.29
Nodes (7): cleanup_voice(), generate_voice(), Удаляет временный аудиофайл после отправки., Синхронная функция для генерации голоса через PyTorch, Генерирует голосовое сообщение из текста.          Args:         text: Текст для, _sync_generate_voice(), test()

### Community 27 - "Community 27"
Cohesion: 0.25
Nodes (4): Форматирует сообщение для передачи менеджеру., Детектор необходимости передачи менеджеру., Проверяет, нужна ли передача менеджеру.                  Returns:             No, SmartHandoff

### Community 28 - "Community 28"
Cohesion: 0.39
Nodes (7): api_call_gemini(), collect_raw_evidence(), log(), Вызывает Gemini для анализа данных., Собирает за день все переписки и звонки для анализа., Анализирует собранные данные и выделяет правила., run_deep_learning()

### Community 29 - "Community 29"
Cohesion: 0.39
Nodes (7): _call_llm(), generate_morning_brief(), log(), post_to_sandbox_feed(), Генерация через OpenRouter., Собирает утренний дайджест., Публикация в Живую Ленту песочницы.

### Community 30 - "Community 30"
Cohesion: 0.29
Nodes (6): extract_summary(), get_manager_names(), is_significant(), Возвращает словарь manager_id → "Имя Фамилия" через Bitrix API.     Если запрос, Определяем значимый звонок.     - Длительность > 120 сек     - В резюме присутст, Извлекает блок РЕЗЮМЕ из транскрипта, если есть.

### Community 31 - "Community 31"
Cohesion: 0.52
Nodes (6): api_call(), download_record(), fetch_new_calls(), load_last_ts(), main(), save_last_ts()

### Community 32 - "Community 32"
Cohesion: 0.29
Nodes (6): extract_summary(), get_manager_names(), is_significant(), Получить словарь manager_id → "Имя Фамилия" через Bitrix API.     Если запрос не, Определяет, является ли звонок значимым.     - Длительность > 120 сек     - В ре, Вернуть текст блока РЕЗЮМЕ (одной строкой) или пустую строку, если нет.

### Community 33 - "Community 33"
Cohesion: 0.4
Nodes (5): fetch_bitrix_products(), Синхронизация товаров из Bitrix24 → angelochka_unified_brain.json Обновляет ката, Загружает все товары из Bitrix24 CRM., Синхронизирует товары Bitrix → brain., sync_products()

### Community 34 - "Community 34"
Cohesion: 0.33
Nodes (3): CallAnalyzer, Анализатор аудио-звонков на базе Gemini 2.5 Flash, Загружает аудио файл в Google API и анализирует его

### Community 35 - "Community 35"
Cohesion: 0.47
Nodes (5): main(), Загрузка файла на Общий диск Битрикс24., Отправка сообщения в песочницу., send_message(), upload_to_disk()

### Community 36 - "Community 36"
Cohesion: 0.67
Nodes (3): analyze(), find_richest_scan(), Находит скан с наибольшим объёмом данных.

### Community 37 - "Community 37"
Cohesion: 0.67
Nodes (2): Отправляет сообщение в Битрикс24 мессенджер., send_bitrix_message()

### Community 39 - "Community 39"
Cohesion: 0.67
Nodes (2): Отправляет сообщение в песочницу Битрикс24., send_sandbox_message()

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (2): clean_feed(), publish_working_article()

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (2): clean_feed(), publish_working_article()

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (2): bitrix_call(), scan_sandbox()

### Community 47 - "Community 47"
Cohesion: 0.67
Nodes (2): get_manager_names(), Возвращает словарь manager_id → "Имя Фамилия" через Bitrix API.

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (2): markdown_to_bbcode(), publish_perfect_article()

### Community 49 - "Community 49"
Cohesion: 0.67
Nodes (1): Отправка отчёта по IT-инфраструктуре Андрею и Игорю в TG.

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (2): markdown_to_bbcode(), publish_formatted_article()

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (2): clean_feed(), publish_working_article()

### Community 53 - "Community 53"
Cohesion: 0.67
Nodes (1): Аналитика менеджеров за последний месяц. Собирает звонки, сделки, конверсию.

### Community 54 - "Community 54"
Cohesion: 0.67
Nodes (2): create_lead(), Создаёт лид в Bitrix24 CRM.          Args:         name: Имя клиента         pho

### Community 84 - "Community 84"
Cohesion: 1.0
Nodes (1): Проверить работоспособность API.

### Community 85 - "Community 85"
Cohesion: 1.0
Nodes (1): Отправить SMS. Возвращает {'success': bool, 'message_id': str, 'error': str}

### Community 86 - "Community 86"
Cohesion: 1.0
Nodes (1): Проверить баланс. Возвращает сумму в рублях.

### Community 87 - "Community 87"
Cohesion: 1.0
Nodes (1): Статус доставки: 'delivered', 'sent', 'failed', 'unknown'.

## Knowledge Gaps
- **290 isolated node(s):** `Сообщение между агентами.`, `Файловая шина обмена сообщениями.`, `Публикует сообщение в шину.`, `Получает все сообщения для агента.`, `Помечает сообщение как прочитанное.` (+285 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 37`** (3 nodes): `Отправляет сообщение в Битрикс24 мессенджер.`, `send_bitrix_message()`, `send_to_bitrix.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (3 nodes): `Отправляет сообщение в песочницу Битрикс24.`, `send_sandbox_message()`, `send_to_sandbox.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (3 nodes): `clean_feed()`, `publish_working_article()`, `sandbox_publish_chicks.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (3 nodes): `clean_feed()`, `publish_working_article()`, `sandbox_publish_picsum.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (3 nodes): `bitrix_call()`, `scan_sandbox()`, `sandbox_scanner.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (3 nodes): `get_manager_names()`, `Возвращает словарь manager_id → "Имя Фамилия" через Bitrix API.`, `test_report_fragment.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (3 nodes): `markdown_to_bbcode()`, `publish_perfect_article()`, `sandbox_publish_glossy.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (3 nodes): `Отправка отчёта по IT-инфраструктуре Андрею и Игорю в TG.`, `send_tg()`, `send_infra_report.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (3 nodes): `markdown_to_bbcode()`, `publish_formatted_article()`, `sandbox_publish_formatted.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (3 nodes): `clean_feed()`, `publish_working_article()`, `sandbox_publish_final.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (3 nodes): `bitrix_batch()`, `Аналитика менеджеров за последний месяц. Собирает звонки, сделки, конверсию.`, `manager_analytics.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (3 nodes): `create_lead()`, `Создаёт лид в Bitrix24 CRM.          Args:         name: Имя клиента         pho`, `bitrix_lead.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 84`** (1 nodes): `Проверить работоспособность API.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 85`** (1 nodes): `Отправить SMS. Возвращает {'success': bool, 'message_id': str, 'error': str}`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 86`** (1 nodes): `Проверить баланс. Возвращает сумму в рублях.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 87`** (1 nodes): `Статус доставки: 'delivered', 'sent', 'failed', 'unknown'.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_answer()` connect `Community 8` to `Community 0`, `Community 24`, `Community 3`, `Community 1`?**
  _High betweenness centrality (0.087) - this node is a cross-community bridge._
- **Why does `process_message_with_avito_detection()` connect `Community 1` to `Community 8`, `Community 3`?**
  _High betweenness centrality (0.058) - this node is a cross-community bridge._
- **Why does `Avitolog` connect `Community 1` to `Community 6`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `MemoryGraph` (e.g. with `SmartFAQ` and `Проверяет, оставил ли клиент телефон в истории диалога.     Phone-First Protocol`) actually correct?**
  _`MemoryGraph` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `VectorMemory` (e.g. with `SmartFAQ` and `Проверяет, оставил ли клиент телефон в истории диалога.     Phone-First Protocol`) actually correct?**
  _`VectorMemory` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `Avitolog` (e.g. with `ForcedIPResolver` and `IPv4AiohttpSession`) actually correct?**
  _`Avitolog` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `AngelochkaVectorDB` (e.g. with `SmartFAQ` and `Проверяет, оставил ли клиент телефон в истории диалога.     Phone-First Protocol`) actually correct?**
  _`AngelochkaVectorDB` has 12 INFERRED edges - model-reasoned connections that need verification._