# AI-EGGS — Проектная документация
# Всё что нужно знать агенту при работе с этим проектом.
# Обновлено: 2026-04-30

---

## 📋 О проекте

AI-EGGS (IncuBird / ВезёмЦыплят) — AI-инфраструктура для птицеводческого бизнеса.
Два AI-агента: **Заботкина** (CRM, продажи) и **Птенчикова** (маркетинг, продвижение).

---

## 🖥 VPS (Timeweb)

Все процессы крутятся на `root@72.56.38.19`.
Python venv: `/root/antigravity/ai-eggs/venv/`
Код: `/root/antigravity/ai-eggs/agent/`

### PM2 процессы (ecosystem.config.js)

| Процесс | Скрипт | Назначение |
|---------|--------|------------|
| `angela-scheduler` | scheduler.py | 09:00 Хабр, 19:00 Скан CRM, 20:00 Отчёт Заботкиной |
| `angela-autopilot` | autopilot.py | 09:00 Пинг, 20:05 Отчёт Птенчиковой, 21:00 Спокойной ночи |
| `angela-bot` | tg_bot.py | TG-бот Анжелочки (/report /status /silent /voice) |
| `angela-server` | server.py | FastAPI backend (порт 5000) |
| `ptenchikova-bot` | feed_interactor.py | Feed Interactor Bot |
| `vezem-web` | — | Сайт VezemCip (Astro SSR, порт 4321) |

### Деплой

```bash
rsync -avz -e "ssh -i /Users/igorvasin/freelance-2026/.ssh_agent_key -o StrictHostKeyChecking=no" \
  --exclude='venv/' --exclude='__pycache__/' --exclude='logs/' --exclude='data/bitrix_scans/' \
  /Users/igorvasin/freelance-2026/ai-eggs/agent/ root@72.56.38.19:/root/antigravity/ai-eggs/agent/
```

После синхронизации:
```bash
ssh -i ... root@72.56.38.19 'cd /root/antigravity/ai-eggs/agent && pm2 delete all && pm2 start ecosystem.config.js && pm2 save'
```

---

## 🧠 LLM Каскад (OpenRouter)

### Основной каскад (angelochka_core.py → `_call_openrouter`):
1. `xiaomi/mimo-v2.5-pro` — MiMo-v2.5 Pro (основная)
2. `moonshotai/moonshot-v1-32k` — Kimi
3. `perplexity/llama-3.1-sonar-large-128k-chat` — Perplexity
4. `anthropic/claude-3.5-sonnet` — Sonnet
5. `deepseek/deepseek-chat` — DeepSeek
6. `openrouter/auto` — Резерв

### Каскад отчёта Заботкиной (daily_report.py):
1. `moonshotai/moonshot-v1-32k` — Kimi
2. `deepseek/deepseek-chat` — DeepSeek
3. `google/gemini-2.5-flash-preview` — Gemini Flash

### Глобальный порядок (`call_llm`):
OpenRouter → Gemini Direct (через прокси) → Ollama/Gemma4 (оффлайн)

---

## ⏰ Расписание отчётов (MSK)

| Время | Кто | Что |
|-------|-----|-----|
| 09:00 | scheduler | 📰 Хабр-дайджест |
| 09:00 | autopilot | 🌅 Утренний пинг «система жива» |
| 19:00 | scheduler | 🔍 Скан CRM Битрикс24 |
| 20:00 | scheduler | 📋 Отчёт Заботкиной (CRM + AI каскад 3 модели) |
| 20:05 | autopilot | 🚀 Отчёт Птенчиковой (project_report.py) |
| 21:00 | autopilot | 🌙 «День закончен, отдыхайте!» |

---

## 🤖 TG-бот (tg_bot.py)

Команды (только для админа, ID 176203333):
- `/report` — полный отчёт CRM + AI-аналитика
- `/status` — статус системы
- `/silent` — тихий режим
- `/voice` — голосовой режим

---

## 📁 Ключевые файлы

```
ai-eggs/
├── agent/
│   ├── angelochka_core.py     ← Ядро: LLM каскад, промпты, роли
│   ├── tg_bot.py              ← Telegram-бот
│   ├── scheduler.py           ← Планировщик (09:00, 19:00, 20:00)
│   ├── autopilot.py           ← Автопилот (20:05 Птенчикова)
│   ├── daily_report.py        ← Отчёт Заботкиной + AI
│   ├── project_report.py      ← Отчёт Птенчиковой
│   ├── health_monitor.py      ← Мониторинг + auto-heal
│   ├── ecosystem.config.js    ← PM2 конфиг (единственный источник правды)
│   ├── sales_logic.py         ← Слой продаж
│   ├── feed_calculator.py     ← Калькулятор кормов
│   └── deploy_to_vps.sh       ← Скрипт деплоя
├── data/                      ← Данные (FAQ, brain, сканы)
└── .env                       ← API ключи
```
