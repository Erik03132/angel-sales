# AGENTS.md — Контекст проекта AI Eggs

AI-EGGS (IncuBird / ВезёмЦыплят) — AI-инфраструктура для птицеводческого бизнеса:
**Заботкина** (CRM, продажи) + **Птенчикова** (маркетинг, продвижение).

**Ключевые документы:** `PROJECT.md`, `STATUS.md`, `UNIFIED_ROADMAP.md`

**VPS:** `root@72.56.38.19` (Timeweb), PM2 на 5 процессах.
**Локальный запуск:** `ai-eggs/agent/` — ядро, бот, планировщик, отчёты.

**Фото-каскад (правило):** Leonardo AI → всегда первый. FAL Flux → fallback. Стоки (Unsplash/Pexels/Pixabay) → последний резерв. Imagen 3/4 — НЕ использовать (только платный план).

## 🎙️ Voice Angela (голосовой ассистент)

**Создана 16.06.2026.** Голос Kore (Gemini TTS), Angela (OpenRouter DeepSeek + локальный Ollama fallback), STT (Whisper base).

| Компонент | Файл | PM2 | Что делает |
|-----------|------|-----|------------|
| Voice bridge | `agent/voice_bridge.py` | `voice-angela` (id 21) | Входящие звонки через baresip |
| Outbound calls | `agent/angela_outbound.py` | — | Исходящий обзвон + заказ в Битрикс |
| Local web test | `agent-lab/voice_angela_web.py` | — (localhost:9090) | Веб-интерфейс + кеш |
| Local simulator | `agent/test_voice_local.py` | — | Симуляция звонка без Mango |
| Mango webhook | `/opt/mango_webhook.py` | `mango-webhook` (id 8) | Приём событий Mango |
| Test call | `agent/test_voice_call.py` | — | Тестовый callback |
| Спек | `docs/superpowers/specs/2026-06-16-realtime-voice-angela.md` | — | Спецификация |

**Eval suite:** `python3 tests/eval_angela.py` — прогонять перед изменениями промптов/моделей/router/FAQ. 47 тестов: Router (regression+capability) + FAQ (точность, алиасы, negative synonyms).

**LLM каскад:** OpenRouter DeepSeek → Qwen 2.5 → локальный Ollama llama3.2:1b (fallback)
**TTS каскад:** Gemini Kore (через SOCKS5 прокси)

**Тестовый номер:** `+7(861)202-51-10` (Краснодар, ожидает оплаты)
**SIP extension:** `user4@vpbx400161137.mangosip.ru`
**VPS baresip:** `72.56.38.19:5060`, auto_answer=yes

**Важно:** 
- Gemini TTS Kore работает только через SOCKS5 прокси (РФ заблокирован)
- Основной номер не должен звонить на user4 — только тестовый
- OpenRouter из РФ: 2-3 сек (короткий промпт), до 40 сек (полный прайс)

> Каскадная система, список глобальных скиллов и правила эскалации — в `~/.config/opencode/AGENTS.md`.

---

## Команды сессии

### `start-day-ai-eggs` — Старт сессии

1. **Прочитать регламенты:** `AGENTS.md` + `chp.md` + последний `projects/ai-eggs/checkpoints/chp_*.md`
2. **claude-mem:** `memory_search("ai-eggs")` — подтянуть историю сессий
3. **Git:** `git status` — проверить незакоммиченные изменения
4. **.env:** проверить ключи: `MANGO_VPBX_API_KEY`, `MANGO_VPBX_API_SALT`, `VPS_IP`, `GEMINI_API_KEY` — не пустые
5. **Handoff:** проверить `docs/handoff_*.json` — есть ли незавершённые задачи
6. **Скилл:** загрузить `bot-development`
7. Вывести краткую сводку: статус, блокеры, план на сегодня

### `finish-day-ai-eggs` — Завершение сессии

1. **Обновить `chp.md`:** статус, что сделано, блокеры, план на завтра
2. **Копировать `chp.md`** → `checkpoints/chp_<YYYYMMDD_HHMM>.md`
3. **claude-mem:** `memory_add kind=session-summary` с итогами сессии
4. **Git:** `git add -A && git commit -m "..." && git push`
5. Сообщить пользователю: "Сессия завершена"
