# 🔑 VK User Token — обновление (Май 2026)

**Проблема:** User Token истекает через 24 часа после выдачи.

**Текущий статус:** Истёк ~04.05.2026 (10 дней назад)

---

## Как получить новый User Token

### Шаг 1: Открыть OAuth URL

```
https://oauth.vk.com/authorize?client_id=54572099&display=page&redirect_uri=https://oauth.vk.com/blank.html&scope=photos,wall,groups,offline,notifications,email&response_type=token&v=5.199
```

Где:
- `client_id=54572099` — приложение ВезёмЦыплят
- `scope=photos,wall,groups,offline,notifications,email` — все нужные права
- `response_type=token` — вернуть токен сразу (не code)

### Шаг 2: Авторизоваться

1. Открыть URL в браузере ( Safari/Chrome )
2. Войти как владелец сообщества
3. Нажать **Разрешить**
4. Браузер перенаправит на `https://oauth.vk.com/blank.html#access_token=XXX...`

### Шаг 3: Скопировать токен

Из адресной строки скопировать значение `access_token`:
```
https://oauth.vk.com/blank.html#access_token=vk1.a.XXXXXX...
                                         ^^^^^^^^^^^^^^^^
                                         ЭТО НОВЫЙ ТОКЕН
```

### Шаг 4: Обновить .env

```bash
# В /Users/igorvasin/freelance-2026/ai-eggs/.env
VK_USER_TOKEN=vk1.a.НОВЫЙ_ТОКЕН_ЗДЕСЬ
```

### Шаг 5: Проверить токен

```bash
curl -s "https://api.vk.com/method/account.getAppPermissions?access_token=vk1.a.XXX&v=5.199"
```

Ответ `{"response":1}` — токен работает.

---

## Срок действия

- **User Token:** 24 часа (официально), но может жить дольше с `offline` scope
- **Group Token:** бессрочный (но не может загружать фото)
- **Refresh:** запускать `photo_cache_builder.py build` раз в 1-3 дня

---

## Альтернатива: Server Token (бессрочный)

Если нужен бессрочный токен для сервера:

1. Зайти в https://vk.com/dev
2. Мои приложения → ВезёмЦыплят (54572099)
3. Настройки → Server Token
4. Скопировать → `.env` как `VK_SERVER_TOKEN`

**Но:** Server Token не имеет прав на загрузку фото (только чтение).

---

*15 мая 2026 | Инструкция по обновлению VK User Token*
