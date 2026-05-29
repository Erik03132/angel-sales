# 🔑 VK API — Получение User Token (OAuth)

## Рабочие приложения для OAuth

| # | App ID | Название | Статус |
|---|--------|----------|--------|
| 1 | 51421669 | (кастомное) | ❌ disabled |
| 2 | 2274003 | VK Android | ❌ "Unavailable for apps with direct auth" |
| 3 | **2685278** | **Kate Mobile** | ✅ РАБОТАЕТ |
| 4 | 6121396 | VK Admin | ? не проверено |

## Формат OAuth URL
```
https://oauth.vk.com/authorize?client_id={APP_ID}&display=page&redirect_uri=https://oauth.vk.com/blank.html&scope={SCOPES}&response_type=token&v=5.199
```

## Важные scope для наших задач
| Scope | Бит | Нужен для |
|-------|-----|-----------|
| photos | 2 | Загрузка фото в альбомы, wall |
| wall | 11 | Публикация постов |
| groups | 15 | Управление сообществами |
| offline | 13 | Бессрочный токен |
| **market** | **20** | **Загрузка фото в каталог товаров** |

## ⚠️ Проблема: Kate Mobile (2685278) НЕ выдаёт scope `market`
Даже если указать `scope=market` — токен выходит без этого права.
Mask 134553604 = photos + offline (без market).

## Решение: создать своё Standalone-приложение
1. Зайти на https://vk.com/editapp?act=create
2. Тип: **Standalone-приложение**
3. Название: любое (например "AI Eggs Admin")
4. После создания → Настройки → скопировать **ID приложения**
5. Включить нужные права в настройках
6. Использовать OAuth URL с этим app_id

## Проверка прав токена
```bash
curl -s "https://api.vk.com/method/account.getAppPermissions?access_token=TOKEN&v=5.199"
# response → mask число, проверить бит 20 (market): mask & (1<<20)
```

## Текущие токены (.env)
- `VK_USER_TOKEN` — user token (scope: photos, offline, groups, notifications, email)
- `VK_VEZEMCYP_TOKEN` — group token (сообщество #ВеземЦып)
- `VK_PODVORYE_TOKEN` — group token (Своё Подворье)
