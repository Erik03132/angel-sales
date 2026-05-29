#!/bin/bash
# ============================================================
# 🚀 ДЕПЛОЙ САЙТА vezemcip.ru
# ============================================================
# 
# АРХИТЕКТУРА ПРОДАКШЕНА:
#   Сервер:     72.56.38.19 (Timeweb/Hostia VDS, Ubuntu)
#   Пароль:     zE4qDJb-+Y+rv+
#   Nginx:      proxy_pass → http://localhost:4321/
#   PM2:        процесс "vezem-web" (Astro Node.js standalone)
#   Файлы:      /root/antigravity/ai-eggs/vezem/dist/client/
#   
# ВАЖНО:
#   - Nginx НЕ раздаёт статику!
#   - Nginx проксирует на Node.js (порт 4321)
#   - PM2 запускает Astro сервер из /root/antigravity/ai-eggs/vezem/
#   - После заливки файлов ОБЯЗАТЕЛЬНО pm2 restart vezem-web
#
# ИСПОЛЬЗОВАНИЕ:
#   ./deploy.sh          — полный деплой (билд + заливка + рестарт)
#   ./deploy.sh --quick  — только заливка dist без пересборки
#
# ============================================================

set -e

SERVER="root@72.56.38.19"
REMOTE_DIST="/root/antigravity/ai-eggs/vezem/dist/client/"
LOCAL_DIST="$(dirname "$0")/dist/client/"
PM2_PROCESS="vezem-web"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${CYAN}🚀 Деплой vezemcip.ru${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# === ШАГ 1: Сборка (если не --quick) ===
if [ "$1" != "--quick" ]; then
    echo -e "\n${YELLOW}📦 Шаг 1: Сборка проекта...${NC}"
    cd "$(dirname "$0")"
    npx astro build
    echo -e "${GREEN}✅ Сборка завершена${NC}"
else
    echo -e "\n${YELLOW}⚡ Быстрый деплой (без пересборки)${NC}"
fi

# === ШАГ 2: Проверка наличия dist ===
if [ ! -f "${LOCAL_DIST}index.html" ]; then
    echo -e "${RED}❌ Файл ${LOCAL_DIST}index.html не найден! Сначала выполни сборку.${NC}"
    exit 1
fi

# Проверяем что виджет есть в билде
WIDGET_CHECK=$(grep -c "consultant-toggle" "${LOCAL_DIST}index.html" || true)
if [ "$WIDGET_CHECK" -eq 0 ]; then
    echo -e "${RED}⚠️ ВНИМАНИЕ: Виджет Анжелочки НЕ найден в index.html!${NC}"
    read -p "Продолжить деплой? (y/n): " -n 1 -r
    echo
    [[ ! $REPLY =~ ^[Yy]$ ]] && exit 1
else
    echo -e "${GREEN}✅ Виджет Анжелочки найден в билде${NC}"
fi

# === ШАГ 3: Заливка на сервер ===
echo -e "\n${YELLOW}📤 Шаг 2: Заливка файлов на сервер...${NC}"
echo -e "   Сервер: ${CYAN}${SERVER}${NC}"
echo -e "   Путь:   ${CYAN}${REMOTE_DIST}${NC}"
rsync -avz --delete "${LOCAL_DIST}" "${SERVER}:${REMOTE_DIST}"
echo -e "${GREEN}✅ Файлы залиты${NC}"

# === ШАГ 4: Перезапуск PM2 ===
echo -e "\n${YELLOW}🔄 Шаг 3: Перезапуск ${PM2_PROCESS}...${NC}"
ssh "${SERVER}" "pm2 restart ${PM2_PROCESS}"
echo -e "${GREEN}✅ Сервер перезапущен${NC}"

# === ШАГ 5: Проверка ===
echo -e "\n${YELLOW}🔍 Шаг 4: Проверка...${NC}"
sleep 2
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" https://vezemcip.ru/)
if [ "$HTTP_CODE" = "200" ]; then
    LIVE_WIDGET=$(curl -s https://vezemcip.ru/ | grep -c "consultant-toggle" || true)
    if [ "$LIVE_WIDGET" -gt 0 ]; then
        echo -e "${GREEN}✅ Сайт работает (HTTP ${HTTP_CODE}), виджет на месте!${NC}"
    else
        echo -e "${YELLOW}⚠️ Сайт работает (HTTP ${HTTP_CODE}), но виджет НЕ найден!${NC}"
    fi
else
    echo -e "${RED}❌ Сайт вернул HTTP ${HTTP_CODE}!${NC}"
fi

echo -e "\n${GREEN}🎉 Деплой завершён!${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "🌐 https://vezemcip.ru/"
