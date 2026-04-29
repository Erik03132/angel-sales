#!/bin/bash
# =======================================================
# DEPLOY ANGELA TO VPS — Полный деплой + синхронизация
# VPS: root@72.56.38.19 (НОВЫЙ СЕРВЕР от 20.04.2026)
#
# ТРЕБОВАНИЯ: SSH-ключ (запусти setup_ssh_key.sh один раз)
# Использование: bash deploy_to_vps.sh
# =======================================================

VPS_USER="root"
VPS_IP="72.56.38.19"
VPS_DIR="/root/antigravity/ai-eggs"
LOCAL_DIR="/Users/igorvasin/freelance-2026/ai-eggs"

echo "🚀 DEPLOY ANGELA → VPS ($VPS_IP)"
echo "================================"

# --- ШАГ 0: Проверяем SSH-доступ ---
echo ""
echo "🔌 ШАГ 0: Проверяем доступность сервера..."
ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes "${VPS_USER}@${VPS_IP}" "echo OK" > /dev/null 2>&1

if [ $? -ne 0 ]; then
    echo "⚠️  SSH-ключ не настроен или сервер недоступен."
    echo "   Пробую подключиться с запросом пароля..."
    echo "   (Пароль: zE4qDJb-+Y+rv+)"
    echo ""
    ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no "${VPS_USER}@${VPS_IP}" "echo OK" > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo "❌ Сервер ${VPS_IP} недоступен! Проверь IP/пароль/файрвол."
        echo "   Попробуй сначала: bash setup_ssh_key.sh"
        exit 1
    fi
    SSH_OPTS="-o StrictHostKeyChecking=no"
else
    SSH_OPTS="-o StrictHostKeyChecking=no -o BatchMode=yes"
fi
echo "✅ Сервер доступен"

# --- ШАГ 1: Синхронизируем код агента ---
echo ""
echo "📁 ШАГ 1: Синхронизируем код агента..."
rsync -avz --progress -e "ssh ${SSH_OPTS}" \
    --exclude='venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='logs/' \
    --exclude='data/bitrix_scans/' \
    --exclude='data/sandbox_scans/' \
    --exclude='v4_ru.pt' \
    --exclude='dummy_call.aiff' \
    "${LOCAL_DIR}/agent/" \
    "${VPS_USER}@${VPS_IP}:${VPS_DIR}/agent/"

# --- ШАГ 2: Синхронизируем .env и данные ---
echo ""
echo "📊 ШАГ 2: Синхронизируем .env и данные..."
rsync -avz --progress -e "ssh ${SSH_OPTS}" \
    "${LOCAL_DIR}/.env" \
    "${VPS_USER}@${VPS_IP}:${VPS_DIR}/.env"

rsync -avz --progress -e "ssh ${SSH_OPTS}" \
    --exclude='bitrix_scans/' \
    --exclude='sandbox_scans/' \
    --exclude='daily_reports/' \
    "${LOCAL_DIR}/data/" \
    "${VPS_USER}@${VPS_IP}:${VPS_DIR}/data/"

# --- ШАГ 3: Синхронизируем requirements ---
echo ""
echo "📦 ШАГ 3: Синхронизируем requirements.txt..."
rsync -avz -e "ssh ${SSH_OPTS}" \
    "${LOCAL_DIR}/requirements.txt" \
    "${VPS_USER}@${VPS_IP}:${VPS_DIR}/requirements.txt" 2>/dev/null

# --- ШАГ 4: Настраиваем PM2 + venv на VPS ---
echo ""
echo "♻️  ШАГ 4: Настраиваем PM2 + venv на VPS..."
ssh ${SSH_OPTS} "${VPS_USER}@${VPS_IP}" << 'REMOTE_SETUP'
    echo "--- Настройка на VPS ---"
    
    cd /root/antigravity/ai-eggs/

    # Создаём venv если нет
    if [ ! -d "venv" ]; then
        echo "🐍 Создаём venv..."
        python3 -m venv venv
    fi

    # Устанавливаем зависимости
    echo "📦 Устанавливаем зависимости..."
    venv/bin/pip install -q python-dotenv requests httpx 2>/dev/null
    if [ -f "requirements.txt" ]; then
        venv/bin/pip install -q -r requirements.txt 2>/dev/null
    fi

    cd agent/

    # Убиваем старые scheduler процессы
    pm2 delete angela-scheduler 2>/dev/null
    
    # Проверяем есть ли ecosystem.config.js
    if [ -f "ecosystem.config.js" ]; then
        echo "⚙️  Запуск через ecosystem.config.js..."
        pm2 start ecosystem.config.js --only angela-scheduler
    else
        echo "⚙️  Запуск через CLI..."
        pm2 start scheduler.py \
            --name angela-scheduler \
            --interpreter /root/antigravity/ai-eggs/venv/bin/python3 \
            --cwd /root/antigravity/ai-eggs/agent/ \
            -- 
    fi
    
    # Перезапускаем основного бота (если есть)
    pm2 restart angelochka 2>/dev/null || \
    pm2 restart angela 2>/dev/null || \
    pm2 restart angela-zabotkina 2>/dev/null || \
    echo "ℹ️  Основной бот не найден в PM2 (это ок если он не настроен)"

    # Сохраняем PM2 для автозапуска после reboot
    pm2 save
    
    echo ""
    echo "📋 PM2 STATUS:"
    pm2 list
REMOTE_SETUP

# --- ШАГ 5: Настраиваем CRON как FALLBACK ---
echo ""
echo "⏰ ШАГ 5: Настраиваем cron-watchdog + fallback на VPS..."
ssh ${SSH_OPTS} "${VPS_USER}@${VPS_IP}" << 'CRONEOF'
    VENV_PYTHON="/root/antigravity/ai-eggs/venv/bin/python3"
    REPORTER="/root/antigravity/ai-eggs/agent/daily_report.py"
    CALL_QUALITY="/root/antigravity/ai-eggs/agent/call_quality_report.py"
    LOG_DIR="/root/antigravity/ai-eggs/agent/logs"
    
    mkdir -p "$LOG_DIR"
    
    # Создаём watchdog скрипт
    WATCHDOG="/root/antigravity/ai-eggs/agent/watchdog_cron.sh"
    
    cat > "$WATCHDOG" << 'WD'
#!/bin/bash
# Watchdog — перезапускает scheduler если heartbeat устарел
HEARTBEAT="/root/antigravity/ai-eggs/agent/logs/scheduler_heartbeat.json"

if [ ! -f "$HEARTBEAT" ]; then
    echo "[$(date)] WATCHDOG: heartbeat не найден, перезапускаю scheduler"
    pm2 restart angela-scheduler 2>/dev/null
    exit 0
fi

# Проверяем возраст heartbeat файла (> 600 секунд = 10 минут)
HEARTBEAT_AGE=$(( $(date +%s) - $(stat -c %Y "$HEARTBEAT" 2>/dev/null || stat -f %m "$HEARTBEAT" 2>/dev/null || echo 0) ))
if [ "$HEARTBEAT_AGE" -gt 600 ]; then
    echo "[$(date)] WATCHDOG: heartbeat устарел (${HEARTBEAT_AGE}с), перезапускаю scheduler"
    pm2 restart angela-scheduler 2>/dev/null
fi
WD
    
    chmod +x "$WATCHDOG"
    
    # Записываем ПОЛНЫЙ crontab (3 уровня защиты)
    (crontab -l 2>/dev/null | grep -v watchdog_cron | grep -v daily_report | grep -v health_monitor | grep -v bitrix_scanner | grep -v call_quality_report; \
     echo "# === LEVEL 2: Watchdog ==="; \
     echo "*/15 * * * * $WATCHDOG >> $LOG_DIR/watchdog.log 2>&1"; \
     echo "# === LEVEL 2: Fallback отчёт 20:10 ==="; \
     echo "10 20 * * * $VENV_PYTHON $REPORTER >> $LOG_DIR/report_cron_fallback.log 2>&1"; \
     echo "# === LEVEL 2: Fallback отчёт по звонкам 20:12 ==="; \
     echo "12 20 * * * $VENV_PYTHON $CALL_QUALITY >> $LOG_DIR/call_quality_cron_fallback.log 2>&1"; \
     echo "# === LEVEL 3: Health Monitor каждые 30 мин ==="; \
     echo "*/30 * * * * $VENV_PYTHON /root/antigravity/ai-eggs/agent/health_monitor.py >> $LOG_DIR/health_monitor.log 2>&1") | crontab -
    
    echo "✅ Cron настроен:"
    crontab -l
CRONEOF

# --- ШАГ 6: Проверяем здоровье ---
echo ""
echo "🔍 ШАГ 6: Финальная проверка..."
ssh ${SSH_OPTS} "${VPS_USER}@${VPS_IP}" << 'CHECK'
    echo "--- PM2 ---"
    pm2 list
    echo ""
    echo "--- Heartbeat ---"
    cat /root/antigravity/ai-eggs/agent/logs/scheduler_heartbeat.json 2>/dev/null || echo "(пока нет, подождите минуту)"
    echo ""
    echo "--- Scheduler log (последние 5 строк) ---"
    tail -5 /root/antigravity/ai-eggs/agent/logs/scheduler.log 2>/dev/null || echo "(пока пусто)"
CHECK

echo ""
echo "================================"
echo "✅ ДЕПЛОЙ ЗАВЕРШЁН!"
echo "   Ангела на VPS ($VPS_IP) теперь:"
echo "   1. scheduler.py v3.0 под PM2 с heartbeat"
echo "   2. Cron-watchdog перезапускает scheduler если он умер"
echo "   3. Cron-fallback отчёт в 20:10 (страховка)"
echo "   4. Retry-логика: 3 попытки отправки отчёта"
echo ""
echo "📊 Проверь через 2 минуты:"
echo "   ssh root@$VPS_IP 'cat /root/antigravity/ai-eggs/agent/logs/scheduler_heartbeat.json'"
echo "================================"
