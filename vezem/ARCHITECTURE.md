# ВезёмЦыплят - Архитектура системы

## 🏗️ Общая архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│                    ИНТЕРНЕТ (Internet)                          │
│                                                                 │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTPS (Port 443)
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│              DNS: vezemcip.ru → 185.39.206.145                │
│                                                                 │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│           Linux Server (Ubuntu 22.04 LTS)                      │
│           IP: 185.39.206.145                                   │
│                                                                 │
│   ┌───────────────────────────────────────────────────────┐    │
│   │                                                       │    │
│   │   Nginx Web Server (Port 80, 443)                    │    │
│   │   - SSL/TLS Termination (Let's Encrypt)             │    │
│   │   - Reverse Proxy                                    │    │
│   │   - Static Asset Serving                             │    │
│   │   - Load Balancing (если нужно)                      │    │
│   │                                                       │    │
│   └──────────────────────┬────────────────────────────────┘    │
│                          │                                     │
│                          ↓                                     │
│   ┌───────────────────────────────────────────────────────┐    │
│   │                                                       │    │
│   │   Node.js Runtime (v20.19.5)                         │    │
│   │   Process: server.js (PID 26152)                     │    │
│   │   Port: 3000 (localhost only)                        │    │
│   │                                                       │    │
│   │   ┌─────────────────────────────────────────────┐    │    │
│   │   │ Express.js Server                           │    │    │
│   │   │ - GET   /                → Главная страница│    │    │
│   │   │ - POST  /api/submit-order → Прием заказов │    │    │
│   │   │ - GET   /* (fallback)     → SPA routing    │    │    │
│   │   │                                             │    │    │
│   │   │ Middleware:                                 │    │    │
│   │   │ - compression (gzip)                        │    │    │
│   │   │ - express.static (dist/client)              │    │    │
│   │   └─────────────────────────────────────────────┘    │    │
│   │                                                       │    │
│   └───┬───────────────────┬──────────────────┬───────────┘    │
│       │                   │                  │                │
│       ↓                   ↓                  ↓                │
│   ┌──────┐            ┌──────┐          ┌────────┐           │
│   │dist/ │            │.env  │          │PM2     │           │
│   │files │            │file  │          │process │           │
│   │      │            │      │          │manager │           │
│   └──────┘            └──────┘          └────────┘           │
│      ↓                   ↓                                     │
│   /var/www/           /var/www/         /root/.pm2/          │
│   vezemcip/           vezemcip/         startup.sh           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
        │                           │
        │ HTTPS                     │ Internal API
        ↓                           ↓
    ┌────────┐              ┌───────────────┐
    │ Browser│              │ Bitrix24 CRM  │
    │ Client │              │ webhook API   │
    └────────┘              └───────────────┘
        │                           │
        │                           ↓
        │                    CRM Database
        │                   (на Bitrix24)
        │
        └──────────┐
                   ↓
            ┌──────────────────┐
            │ Yandex.Metrika   │
            │ Analytics        │
            │ ID: 104797281    │
            └──────────────────┘
```

---

## 🔄 Жизненный цикл запроса

### 1️⃣ Запрос главной страницы

```
User Browser                    Nginx                Node.js (Express)
     │                            │                        │
     ├─ GET https://vezemcip.ru ─→ Port 443              │
     │                            │                        │
     │                            ├─ SSL/TLS check        │
     │                            │                        │
     │                            ├─ proxy_pass ───────→ localhost:3000
     │                            │                        │
     │                            │           ┌─ app.get('/')
     │                            │           │
     │                            │ ←── Compress (gzip)
     │                            │
     │ ←─ 200 OK (HTML) ──────────┤
     │                            │
     ├─ Parse HTML               │
     │                            │
     ├─ Fetch CSS ───────────────→ Nginx
     ├─ Fetch JS ────────────────→ Nginx  
     ├─ Fetch Images ────────────→ Nginx
     │
     ├─ Load Yandex.Metrika script
     │
     └─ Execute JavaScript
        (React components rendering)
```

### 2️⃣ Добавление товара в корзину

```
Browser (Frontend)
     │
     ├─ User clicks "В корзину"
     │
     ├─ JavaScript handles click
     │
     ├─ Get cart from localStorage
     │
     ├─ Add item to array
     │
     ├─ Save back to localStorage
     │
     ├─ Update UI (cart badge)
     │
     └─ Show Toast notification
```

### 3️⃣ Отправка заказа

```
Browser (Form)                      Express Server                Bitrix24
     │                                   │                           │
     ├─ User fills form                 │                           │
     │ (name, phone, address, items)    │                           │
     │                                   │                           │
     ├─ POST /api/submit-order ────────→ │                           │
     │ (application/json)                │                           │
     │                                   ├─ Parse JSON               │
     │                                   │                           │
     │                                   ├─ Validate data            │
     │                                   │                           │
     │                                   ├─ Get BITRIX24_WEBHOOK     │
     │                                   │ from env                  │
     │                                   │                           │
     │                                   ├─ node-fetch POST ────────→ webhook
     │                                   │ (https://mc.yandex.ru...) │
     │                                   │                           ├─ Create lead
     │                                   │                           │
     │                                   │ ←── 200 OK (Lead created)
     │                                   │                           │
     │ ←── 200 OK (JSON response) ─────┤                           │
     │    { success: true }            │                           │
     │                                   │                           │
     └─ Show success message            │                           │
        Clear cart                       │                           │
                                        │                           │
                                        ├─ Log Yandex.Metrika
                                        │ ecommerce event
```

---

## 📦 Структура папок на сервере

```
/var/www/vezemcip/
├── 📁 dist/                       # Собранный проект
│   ├── 📁 client/                 # Статические файлы для браузера
│   │   ├── index.html             # Главная страница
│   │   ├── 📁 _astro/             # JS/CSS бандлы
│   │   │   ├── OrderForm.astro_astro_type_script_index_0_lang.xxx.js
│   │   │   ├── FloatingCart.astro_astro_type_script_index_0_lang.xxx.js
│   │   │   ├── Products.astro_astro_type_script_index_0_lang.xxx.js
│   │   │   └── *.css              # Оптимизированные CSS файлы
│   │   ├── *.png                  # Изображения птицы
│   │   │   ├── ROSS308.png
│   │   │   ├── Kobb.png
│   │   │   ├── Loman.png
│   │   │   ├── ... и остальные
│   │   ├── favicon.svg            # Иконка сайта
│   │   └── sitemap.xml            # Карта сайта для SEO
│   │
│   └── 📁 server/                 # Серверные файлы
│       └── ...
│
├── server.js                      # Express приложение
├── package.json                   # Зависимости
├── package-lock.json              # Locked версии
├── ecosystem.config.cjs           # PM2 конфигурация
├── node_modules/                  # Установленные пакеты
│   └── (882 packages)
│
├── .env                           # Переменные окружения (опционально)
│
└── 📁 logs/                       # PM2 логи (автоматические)
    ├── vezemcip-error.log
    └── vezemcip-out.log
```

---

## 🔐 Переменные окружения

**Файл:** `ecosystem.config.cjs`

```javascript
module.exports = {
  apps: [{
    name: 'vezemcip',
    script: './server.js',
    instances: 1,
    env: {
      // Переменные окружения
      NODE_ENV: 'production',
      
      // Webhook для Bitrix24
      BITRIX24_WEBHOOK: 'https://vezemcip.bitrix24.ru/rest/1/cwill2a1sdpyntll/crm.lead.add'
    }
  }]
};
```

---

## 🔌 API Endpoints

### POST /api/submit-order

**Назначение:** Отправка заказа в Bitrix24 CRM

**URL:** `https://vezemcip.ru/api/submit-order`

**Метод:** POST

**Content-Type:** application/json

**Request Body:**
```json
{
  "name": "Иван Петров",
  "phone": "+7-918-350-02-25",
  "address": "Краснодар, ул. Советская, д. 123",
  "comment": "Пожалуйста, уточните время доставки",
  "items": [
    {
      "name": "РОСС-308",
      "qty": 100,
      "price": 75
    },
    {
      "name": "Ломан Браун",
      "qty": 50,
      "price": 0  // "По запросу"
    }
  ]
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Заказ успешно отправлен в CRM"
}
```

**Response (Error):**
```json
{
  "success": false,
  "error": "Webhook not configured"
}
```

**Статус коды:**
- `200 OK` - Заказ успешно создан
- `400 Bad Request` - Ошибка валидации
- `500 Internal Server Error` - Ошибка сервера

---

## 🗄️ Данные в базе

### Bitrix24 CRM - Структура лида

Когда заказ отправляется, в Bitrix24 создаётся **Lead** с полями:

| Поле | Тип | Пример | Назначение |
|------|-----|--------|-----------|
| NAME | Text | Иван Петров | Имя клиента |
| PHONE | Phone | +79183500225 | Контактный номер |
| ADDRESS | Text | Краснодар | Адрес доставки |
| COMMENTS | Textarea | Доставить с 10:00 | Дополнительные заметки |
| SOURCE | Select | Website | Источник (сайт) |
| STATUS | Status | NEW | Статус обработки |
| ITEMS | Textarea | РОСС-308 (100 шт) | Список товаров |

---

## 🚀 PM2 Процесс менеджер

### Конфигурация

**Файл:** `/var/www/vezemcip/ecosystem.config.cjs`

```javascript
module.exports = {
  apps: [{
    name: 'vezemcip',            // Имя приложения
    script: './server.js',        // Скрипт для запуска
    instances: 1,                 // 1 экземпляр процесса
    exec_mode: 'fork',            // fork mode (не кластер)
    watch: false,                 // Не перезагружать при изменении
    ignore_watch: ['node_modules'],
    env: {
      NODE_ENV: 'production',
      BITRIX24_WEBHOOK: 'https://vezemcip.bitrix24.ru/rest/1/cwill2a1sdpyntll/crm.lead.add'
    }
  }]
};
```

### Команды PM2

```bash
# Запуск
pm2 start ecosystem.config.cjs

# Остановка
pm2 stop vezemcip

# Перезагрузка
pm2 restart vezemcip

# Удаление
pm2 delete vezemcip

# Просмотр статуса
pm2 status

# Логи
pm2 logs vezemcip

# Env переменные
pm2 env 0

# Сохранение для автозагрузки
pm2 save
pm2 startup
```

---

## 🌐 Nginx конфигурация

**Файл:** `/etc/nginx/sites-available/vezemcip.ru`

```nginx
# HTTP → HTTPS redirect
server {
    listen 80;
    server_name vezemcip.ru www.vezemcip.ru;
    return 301 https://$server_name$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name vezemcip.ru www.vezemcip.ru;

    # SSL certificates from Let's Encrypt
    ssl_certificate /etc/letsencrypt/live/vezemcip.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/vezemcip.ru/privkey.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # GZIP compression
    gzip on;
    gzip_types text/plain text/css text/xml text/javascript 
               application/json application/javascript;

    # Proxy to Node.js
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        
        # Headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        
        # WebSocket support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Static caching
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

---

## 📊 Поток данных (Data Flow)

### При загрузке страницы

```
User Browser
    ↓
GET https://vezemcip.ru
    ↓
[DNS lookup] → 185.39.206.145
    ↓
[SSL/TLS handshake]
    ↓
Nginx (reverse proxy)
    ↓
Node.js Express
    ↓
app.get('/') handler
    ↓
Send dist/client/index.html
    ↓
[Gzip compression]
    ↓
Send to browser (via Nginx)
    ↓
Browser parses HTML
    ↓
Download CSS (dist/client/_astro/*.css)
    ↓
Download JS (dist/client/_astro/*.js)
    ↓
Download images (dist/client/*.png)
    ↓
Load Yandex.Metrika script
    ↓
Execute JavaScript
    ↓
Render UI (React components)
    ↓
Page ready for interaction
```

### При отправке заказа

```
User fills form
    ↓
Click "Отправить"
    ↓
JavaScript validates data
    ↓
POST /api/submit-order
    ↓
[HTTPS transmission]
    ↓
Nginx forwards to Node.js:3000
    ↓
Express parses JSON
    ↓
Validate request
    ↓
Get BITRIX24_WEBHOOK from process.env
    ↓
node-fetch POST to Bitrix24 webhook
    ↓
Bitrix24 API creates lead
    ↓
Response 200 OK
    ↓
Express sends 200 to browser
    ↓
JavaScript shows success toast
    ↓
Clear localStorage (cart)
    ↓
Yandex.Metrika logs ecommerce event
```

---

## 🔄 Кэширование

### Browser Cache
```
Static assets (JS, CSS, images):
Cache-Control: public, immutable, max-age=31536000 (1 год)

HTML pages:
Cache-Control: no-cache (всегда проверяет с сервером)
```

### Server Cache
```
gzip compression: Все responses > 1KB сжимаются
Connection pooling: Reuse TCP connections
```

---

## 📈 Мониторинг и логирование

### PM2 logs

```bash
# Все логи
pm2 logs vezemcip

# Только ошибки
pm2 logs vezemcip --err

# Real-time
pm2 monit vezemcip

# Сохранённые логи
/root/.pm2/logs/vezemcip-out.log
/root/.pm2/logs/vezemcip-error.log
```

### Yandex.Metrika

**События:**
- Pageviews
- Clicks
- Scrolls
- Form submissions (ecommerce)
- Bounce rate

**Доступ:** https://metrica.yandex.ru (ID: 104797281)

---

## 🔐 Безопасность

### SSL/TLS
- ✅ Let's Encrypt сертификат
- ✅ TLS 1.2+ протоколы
- ✅ Сильные cipher suites
- ✅ HSTS header (Strict-Transport-Security)

### Headers
- ✅ X-Content-Type-Options: nosniff
- ✅ X-Frame-Options: SAMEORIGIN
- ✅ X-XSS-Protection: 1; mode=block

### Input Validation
- ✅ Проверка обязательных полей
- ✅ Валидация формата телефона
- ✅ Санитизация текстовых полей

---

## 🚦 Развёртывание процесс

```
1. Local Build
   npm run build
   ↓
2. Archive
   dist.zip
   ↓
3. Upload to server (WinSCP)
   185.39.206.145:/var/www/vezemcip/
   ↓
4. Extract on server
   unzip -o dist.zip
   ↓
5. Install dependencies
   npm install
   ↓
6. Start with PM2
   pm2 start ecosystem.config.cjs
   ↓
7. Save for auto-startup
   pm2 save
   ↓
8. Verify
   pm2 status
   curl https://vezemcip.ru
```

---

## 📞 Troubleshooting

### Сайт не доступен

```bash
# Проверить Nginx
systemctl status nginx
sudo nginx -t

# Проверить Node.js
pm2 status
pm2 logs vezemcip

# Проверить DNS
nslookup vezemcip.ru
```

### API возвращает ошибку

```bash
# Проверить переменные окружения
pm2 env 0

# Проверить доступность Bitrix24
curl -X POST https://vezemcip.bitrix24.ru/rest/1/cwill2a1sdpyntll/crm.lead.add

# Проверить логи Node.js
pm2 logs vezemcip --err
```

### Медленная загрузка

```bash
# Проверить использование памяти
pm2 monit

# Проверить Nginx cache
curl -I https://vezemcip.ru | grep Cache-Control

# Профилировать Node.js
node --prof server.js
```

---

**Версия:** 1.0
**Последнее обновление:** 22 октября 2025
**Статус:** Production Ready ✅
