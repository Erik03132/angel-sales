# Mango Office — настройка

## API Credentials
- **API Endpoint:** `https://app.mango-office.ru/vpbx/`
- **vpbx_api_key:** `a0e6fwgqmjrm6g4qp1zt6ps1sx62ey6f`
- **vpbx_api_salt:** `pabuxia9ssloyg5d8ux49fws2sl7hhdw`

## Внутренние номера
- **22** — SIP: `user4@vpbx400161137.mangosip.ru`
- **25** — тестовый

## Линии
- **73652777654** — городской номер
- **79181805577** — SIP линия

## URL внешней системы

Для работы API нужен URL, куда Mango будет отправлять уведомления.

### Варианты:

1. **Webhook.site (для тестов)**
   - Зайти на https://webhook.site
   - Скопировать уникальный URL
   - Вставить в ЛК Mango

2. **VPS (продакшн)**
   - Поднять простой HTTP сервер на 72.56.38.19
   - Порт: 8080
   - Endpoint: `/mango-webhook`

3. **ngrok (локальная разработка)**
   ```bash
   ngrok http 8080
   ```

### Что принимать:

```python
# POST https://наш-url/vpbx/result/callback
{
    "command_id": "cmd_xxx",
    "result": 1000  # успех или ошибка
}
```

## Статус
- ✅ API работает (баланс 4893.86 RUB)
- ✅ Подпись работает
- ⚠️ Звонки не проходят — нужен URL или настройка в ЛК
