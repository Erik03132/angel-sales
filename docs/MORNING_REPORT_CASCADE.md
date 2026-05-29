# 🔄 КАСКАД + СТРАХОВКА — Утренние отчёты

## 📋 Расписание (MSK)

| Время | Задача | Скрипт | Получатель | Статус |
|-------|--------|--------|------------|--------|
| **02:00** | Ночной аудит кода | `night_audit_vps.sh` | Игорь (TG) | PM2 scheduler |
| **02:01** | 🛡️ Страховка | `night_audit_vps.sh` | — | Cron (если PM2 упал) |
| **03:00** | Транскрибация звонков | `call_transcriber.py --days 1` | — | PM2 scheduler |
| **03:01** | 🛡️ Страховка | `call_transcriber.py --days 1` | — | Cron (если PM2 упал) |
| **08:00** | **ОБЪЕДИНЁННЫЙ отчёт** | `unified_morning_report.py` | Игорь (TG) | PM2 scheduler |
| **08:01** | 🛡️ Страховка | `unified_morning_report.py` | — | Cron (если PM2 упал) |

---

## 🏗️ Архитектура

### Уровень 1: PM2 Scheduler (основной)
```
angela-scheduler (PM2 process)
├── 02:00 → night_audit_vps.sh
├── 03:00 → call_transcriber.py
└── 08:00 → unified_morning_report.py
```

### Уровень 2: Cron (страховка)
```bash
# Проверяет наличие файлов-маркеров
23:01 UTC (02:01 MSK) → night_audit_vps_YYYY-MM-DD.md
00:01 UTC (03:01 MSK) → transcripts/YYYY-MM-DD/
05:01 UTC (08:01 MSK) → unified_reports/unified_YYYY-MM-DD.md
```

### Уровень 3: Watchdog (мониторинг PM2)
```bash
*/5 * * * * → resurrect.sh (если PM2 процесс offline)
```

---

## 📊 Структура отчёта (08:00 MSK)

```
🌞 УТРЕННИЙ ОТЧЁТ — ДД.ММ.ГГГГ ЧЧ:ММ
Данные за ДД.ММ.ГГГГ

══════════════════════════════════════════

💰 CRM ЗА ВЧЕРА
• Сделок: N (на X₽)
• Звонков: N
• Менеджеры: топ-3 по сумме

══════════════════════════════════════════

📞 ТРАНСКРИБАЦИЯ (N звонков)

🏆 Топ пород:
• Бройлер: 10
• Мулард: 5
• ...

💰 Крупные заказы:
• Сделка #XXX — 51 000₽
• Сделка #XXX — 48 000₽
ИТОГО крупных: ~179 000₽+

📈 Качество менеджеров:
• Марина Е: назвались 100%, город 41%, апселл 10%

⚠️ Проблемы:
• Клиент обещал перезвонить: 11
• Отказы клиентов: 3

══════════════════════════════════════════

🌙 НОЧНОЙ АУДИТ (02:00)
• Ruff ошибок: N
• Критических: N

══════════════════════════════════════════

🚀 План на сегодня:
1. Исправить критические ошибки кода
2. Проверить крупные заказы
3. Проконтролировать проблемные звонки
```

---

## 🔧 Файлы

| Файл | Назначение | Путь |
|------|------------|------|
| **Scheduler** | Планировщик задач | `ai-eggs/agent/scheduler.py` |
| **Unified Report** | Объединённый отчёт | `ai-eggs/agent/unified_morning_report.py` |
| **Transcriber** | Транскрибация | `ai-eggs/agent/call_transcriber.py` |
| **Night Audit** | Аудит кода | `tools/night_audit_vps.sh` |
| **Cron (страховка)** | VPS crontab | `ssh root@72.56.38.19 'crontab -l'` |

---

## 🛡️ Как работает страховка

### Пример: PM2 scheduler упал в 01:55

1. **02:00** — PM2 должен был запустить `night_audit_vps.sh` → **НЕ сработал**
2. **02:01** — Cron проверяет: `test ! -f night_audit_vps_2026-05-14.md` → **ФАЙЛА НЕТ**
3. **02:01** — Cron запускает: `night_audit_vps.sh` → **Аудит выполнен**
4. **02:02** — Аудит создаёт файл: `night_audit_vps_2026-05-14.md`
5. **03:00** — PM2 должен был запустить `call_transcriber.py` → **НЕ сработал**
6. **03:01** — Cron проверяет: `test ! -d transcripts/2026-05-13` → **ПАПКИ НЕТ**
7. **03:01** — Cron запускает: `call_transcriber.py --days 1` → **Транскрибация выполнена**

---

## ✅ Проверка статуса

```bash
# 1. Проверка PM2 scheduler
pm2 list | grep angela-scheduler

# 2. Проверка cron-страховки
crontab -l | grep СТРАХОВКА

# 3. Проверка ночного аудита (02:05 MSK)
ls -lt /root/antigravity/reports/night_audit_vps_*.md | head -1

# 4. Проверка транскрибации (03:05 MSK)
ls -d /root/antigravity/ai-eggs/data/transcripts/2026-05-* | tail -1

# 5. Проверка утреннего отчёта (08:05 MSK)
ls -lt /root/antigravity/ai-eggs/data/unified_reports/unified_*.md | head -1
```

---

## 🚨 Аварийный сценарий

**Если ВСЁ упало (PM2 + cron):**

```bash
# Ручной запуск всех трёх задач
cd /root/antigravity

# 1. Ночной аудит
bash tools/night_audit_vps.sh

# 2. Транскрибация
source ai-eggs/venv/bin/activate
python3 ai-eggs/agent/call_transcriber.py --days 1

# 3. Утренний отчёт
python3 ai-eggs/agent/unified_morning_report.py
```

---

## 📅 История изменений

| Дата | Изменение |
|------|-----------|
| 14.05.2026 | Создан `unified_morning_report.py` |
| 14.05.2026 | Добавлена cron-страховка (02:01, 03:01, 08:01) |
| 14.05.2026 | Обновлён scheduler.py (08:00 → unified) |
