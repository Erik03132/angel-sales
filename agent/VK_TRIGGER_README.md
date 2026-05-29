# 🔔 VK TRIGGER — Авто-рассылка из ВК

**Назначение:** При публикации поста в ВК → автоматическая рассылка в TG + MAX + Игорь (ОК)

---

## 📋 Схема работы

```
ВК (Игорь публикует)
    ↓
vk_trigger.py (polling каждые 60 сек)
    ↓
    ├──→ TG канал (@svoye_podvorye)
    ├──→ MAX канал (бизнес-рассылка)
    └──→ TG Игорь (личное) ← "Скопируй в ОК"
```

---

## ⚙️ Настройка

### 1. .env переменные

```bash
# VK (Group Token — бессрочный!)
VK_PODVORYE_GROUP_ID=-238230663
VK_PODVORYE_TOKEN=vk1.a.XXXXXX...

# Telegram
ANGELOCHKA_BOT_TOKEN=XXXXX:YYYYY...
TG_CHANNEL_ID=@svoye_podvorye

# MAX мессенджер
MAX_API_URL=https://api.max.ru/v1/send
MAX_CHANNEL_ID=business_channel
```

### 2. Запуск

```bash
# Старт polling
python3 ai-eggs/agent/vk_trigger.py start

# Статус
python3 ai-eggs/agent/vk_trigger.py status

# Тест
python3 ai-eggs/agent/vk_trigger.py test
```

---

## 📊 Workflow

**1. Игорь публикует пост в ВК**
- Загружает фото из кэша
- Копирует текст из `/ok/YYYY-MM-DD_XX/post.txt`
- Публикует в ВК (wall.post или вручную)

**2. vk_trigger.py видит новый пост**
- Polling VK API каждые 60 сек
- Сравнивает `last_post_id` с текущим

**3. Рассылка**
- **TG:** фото + текст в канал
- **MAX:** фото + текст в бизнес-канал
- **Игорь:** личное сообщение "Скопируй в ОК"

---

## 🎯 Преимущества

| Было (прямая схема) | Стало (VK→) |
|---------------------|-------------|
| User Token (24ч) ❌ | Group Token (бессрочный) ✅ |
| Загрузка фото в ВК | Фото уже в ВК ✅ |
| Генерация контента | Публикация в ВК → рассылка ✅ |
| 5 площадок вручную | 1 публикация → 3 авто ✅ |

---

## 📁 Файлы

| Файл | Назначение |
|------|------------|
| `vk_trigger.py` | Polling ВК + рассылка |
| `vk_trigger_cache.json` | Кэш last_post_id |
| `morning_post.py` | Генерация контента (опционально) |
| `/ok/` | Готовые посты для ВК |

---

## 🧠 Кэш постов

**Кэш ВК фото:** `ai-eggs/data/photo_cache.json`
- 50+ готовых attachment ID
- Не нужно загружать фото каждый раз

**Кэш триггера:** `ai-eggs/data/vk_trigger_cache.json`
- `last_post_id` — последний обработанный пост
- `last_check` — время последней проверки

---

## ⚠️ Troubleshooting

**Ошибка VK API:**
```
❌ VK API ошибка: Invalid access token
```
→ Обновить `VK_PODVORYE_TOKEN` (Group Token, бессрочный)

**TG не отправляет:**
```
❌ TG ошибка: bot was blocked by the user
```
→ Игорь должен нажать `/start` в боте

**MAX не настроен:**
```
⚠️ MAX_API_URL не настроен — пропускаем
```
→ Добавить в `.env`: `MAX_API_URL=...`

---

*16 мая 2026 | Версия 1.0 | VK→TG→MAX→OK workflow*
