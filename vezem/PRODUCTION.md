# 🏗 ПРОДАКШЕН-АРХИТЕКТУРА vezemcip.ru

> **ПРОЧИТАЙ ЭТО ПЕРВЫМ, прежде чем что-то деплоить!**

## 🖥 Сервер

| Параметр | Значение |
|---|---|
| **IP** | `72.56.38.19` |
| **Провайдер** | Timeweb / Hostia |
| **ОС** | Ubuntu |
| **SSH** | `ssh root@72.56.38.19` |
| **Пароль** | `zE4qDJb-+Y+rv+` |
| **Домен** | `vezemcip.ru` |

## 🔧 Как работает сайт (КРИТИЧЕСКИ ВАЖНО!)

```
Браузер → vezemcip.ru 
       → DNS → 72.56.38.19
       → Nginx (proxy_pass)
       → http://localhost:4321
       → Astro Node.js сервер (PM2: "vezem-web")
       → /root/antigravity/ai-eggs/vezem/dist/
```

### ⚠️ Nginx НЕ раздаёт статику!
Nginx работает как **reverse proxy** и перенаправляет ВСЕ запросы на Node.js сервер Astro на порту 4321.

### PM2 процесс
- **Имя**: `vezem-web`
- **Скрипт**: `/usr/bin/bash`
- **CWD**: `/root/antigravity/ai-eggs/vezem`
- **Порт**: 4321

### Путь к файлам на сервере
```
/root/antigravity/ai-eggs/vezem/dist/client/  ← HTML, CSS, JS, картинки
/root/antigravity/ai-eggs/vezem/dist/server/  ← Серверный код Astro
```

### Nginx конфиг
```
/etc/nginx/sites-available/vezemcip
```

## 🚀 Как деплоить

### Способ 1: Автоматический скрипт (рекомендуется)
```bash
cd ~/freelance-2026/ai-eggs/vezem
./deploy.sh           # Полный деплой: билд → заливка → рестарт
./deploy.sh --quick   # Только заливка без пересборки
```

### Способ 2: Ручной деплой
```bash
# 1. Собрать проект
cd ~/freelance-2026/ai-eggs/vezem
npx astro build

# 2. Залить на сервер
rsync -avz --delete dist/client/ root@72.56.38.19:/root/antigravity/ai-eggs/vezem/dist/client/

# 3. Перезапустить сервер (ОБЯЗАТЕЛЬНО!)
ssh root@72.56.38.19 "pm2 restart vezem-web"

# 4. Проверить
curl -s https://vezemcip.ru/ | grep -c "consultant-toggle"
# Должно вернуть 1
```

## ❌ Типичные ошибки

### "Залил файлы, а сайт не обновился"
→ **Перезапусти PM2!** `ssh root@72.56.38.19 "pm2 restart vezem-web"`

### "Залил не в ту папку"
→ Правильный путь: `/root/antigravity/ai-eggs/vezem/dist/client/`  
→ НЕ в `/var/www/vezemcip/` (эта папка не используется nginx!)

### "npm install занимает 40+ минут"
→ Удалены `node_modules`, качает заново. Нормально для первого раза.
→ Если зависло: `npm install --cache /tmp/npm-cache-vezem`

### "astro: command not found"
→ `npx astro build` вместо `astro build`

## 📅 История инцидентов

### 22.04.2026 — Виджет Анжелочки пропал
- **Причина**: На сервере лежала старая сборка `dist/` от 18.04 (до добавления ChatWidget.astro)
- **Решение**: Пересобрали проект, залили в правильную папку, перезапустили PM2
- **Урок**: Всегда деплоить через `deploy.sh` и проверять наличие виджета
