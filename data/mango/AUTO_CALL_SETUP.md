# 📞 Mango Office — полная автоматизация обзвона

## ✅ Что готово

1. **Скрипт автообзвона:** `mango_auto_call_full.py`
2. **Webhook сервер:** `mango_webhook_server.py` (приём DTMF)
3. **Персонализация:** имя, продукция, доставка
4. **DTMF:** 1 = подтвердить, 0 = перенести

---

## 🔧 Настройка в ЛК Mango Office

### Шаг 1: Загрузить MP3 файл

1. Зайти в **office.mango-office.ru**
   - Логин: `16741963`
   - Пароль: `2026incubator!`

2. Раздел **Виртуальная АТС** → **Файлы** (или **Голосовые файлы**)

3. Кнопка **Загрузить файл**

4. Выбрать файл:
   ```
   /Users/igorvasin/freelance-2026/ai-eggs/agent/andrej_call_100_gosyat.mp3
   ```

5. **Запомнить имя файла** в системе (например, `andrej_call_100_gosyat.mp3`)

### Шаг 2: Настроить Webhook URL

1. Раздел **Интеграции** → **API коннектор**

2. Поле **"URL внешней системы"**:
   - Для тестов: `https://webhook.site/xxxx-xxxx-xxxx` (создать на webhook.site)
   - Для продакшена: `http://72.56.38.19:8080/vpbx/result/callback`

3. **Сохранить**

### Шаг 3: Проверить сотрудника

1. Раздел **Сотрудники** → **Номер 25**

2. Убедиться, что:
   - ✅ SIP-клиент подключён
   - ✅ Есть права на исходящие звонки
   - ✅ Номер привязан к линии 73652777654

---

## 🚀 Запуск автообзвона

### Вариант 1: Локальный тест

```bash
# 1. Запустить webhook сервер (в отдельном терминале)
python3 ai-eggs/agent/mango_webhook_server.py --port 8080

# 2. Запустить обзвон
python3 ai-eggs/agent/mango_auto_call_full.py ai-eggs/data/mango/clients.csv --delay 30
```

### Вариант 2: На VPS (продакшн)

```bash
# 1. Запустить webhook сервер на VPS
ssh 72.56.38.19
cd ~/ai-eggs/agent
nohup python3 mango_webhook_server.py --port 8080 > webhook.log 2>&1 &

# 2. В ЛК Mango указать URL: http://72.56.38.19:8080/vpbx/result/callback

# 3. Запустить обзвон
python3 mango_auto_call_full.py clients.csv --delay 30
```

### Вариант 3: С ngrok (локально с публичным URL)

```bash
# 1. Запустить ngrok
ngrok http 8080

# 2. Скопировать URL (например, https://xxxx.ngrok.io)

# 3. В ЛК Mango указать: https://xxxx.ngrok.io/vpbx/result/callback

# 4. Запустить webhook и обзвон
python3 ai-eggs/agent/mango_webhook_server.py --port 8080
python3 ai-eggs/agent/mango_auto_call_full.py clients.csv --delay 30
```

---

## 📊 Формат CSV

```csv
name,phone,product,delivery_location
Игорь,+79859234644,125 цыплят,Джанкой
Андрей,+79991234567,100 гусят,Керчь
Иван,+79781234567,50 бройлеров,Симферополь
```

---

## 📝 Скрипт звонка (17 секунд)

```
{Имя}, добрый вечер! Это Анжела, Азовский Инкубатор.
Вы заказали {продукция} на доставку в {доставка}.
Водитель позвонит вам завтра.
Для подтверждения — нажмите 1.
Для переноса — нажмите 0.
Спасибо!
```

**Пример:**
```
Игорь, добрый вечер! Это Анжела, Азовский Инкубатор.
Вы заказали 125 цыплят на доставку в Джанкой.
Водитель позвонит вам завтра.
Для подтверждения — нажмите 1.
Для переноса — нажмите 0.
Спасибо!
```

---

## 📁 Лог файлы

| Файл | Описание |
|------|----------|
| `auto_call_log.jsonl` | Все звонки (инициация) |
| `callback_results.jsonl` | Результаты звонков (успех/ошибка) |
| `dtmf_events.jsonl` | DTMF нажатия (1 или 0) |

---

## 🎯 Результат

После обзвона в логах будет:

```json
{
  "timestamp": "2026-05-15T22:30:00",
  "name": "Игорь",
  "phone": "+79859234644",
  "product": "125 цыплят",
  "delivery": "Джанкой",
  "result": {"command_id": "cmd_xxx", "result": 1000},
  "dtmf_status": "1"  // или "0"
}
```

---

## ⚠️ Важно

1. **MP3 файл должен быть загружен в ЛК Mango** перед звонками
2. **Webhook URL должен быть указан в настройках API** для приёма DTMF
3. **Пауза между звонками:** минимум 10 сек (рекомендуется 30 сек)
4. **Лимиты API:** 10 звонков в секунду, 100 звонков всего

---

## 🆘 Troubleshooting

### Звонок инициирован, но MP3 не играет

- Проверить, что файл загружен в ЛК Mango
- Проверить имя файла в переменной `MP3_FILENAME`

### DTMF не собираются

- Проверить, что Webhook URL указан в ЛК Mango
- Запустить `mango_webhook_server.py` для приёма событий

### Ошибка 3330

- Номер сотрудника не найден — проверить настройки в ЛК
- Использовать правильный `FROM_EXTENSION` и `FROM_NUMBER`

### Ошибка 401

- Неверная подпись — проверить `VPBX_API_KEY` и `VPBX_API_SALT`

---

## 📞 Команды

```bash
# Тест одного звонка
python3 ai-eggs/agent/mango_auto_call_full.py ai-eggs/data/mango/clients.csv --test +79859234644

# Массовый обзвон с паузой 30 сек
python3 ai-eggs/agent/mango_auto_call_full.py clients.csv --delay 30

# Запуск webhook сервера
python3 ai-eggs/agent/mango_webhook_server.py --port 8080

# Просмотр логов
tail -f ai-eggs/data/mango/auto_call_log.jsonl
tail -f ai-eggs/data/mango/dtmf_events.jsonl
```

---

*15 мая 2026 | Версия 1.0 | Полная автоматизация*
