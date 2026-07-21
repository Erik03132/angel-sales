#!/bin/bash
# =======================================================
# DEPLOY ANGELA TO VPS — Полный деплой + синхронизация
#
# Конфиг читается из ../.env:
#   VPS_HOST, VPS_USER, VPS_PASS, VPS_SSH_KEY
#
# Использование: bash deploy_to_vps.sh
# =======================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env"

# --- Безопасное чтение .env (не интерпретирует & ! $ и т.п.) ---
if [ -f "$ENV_FILE" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in ''|\#*) continue ;; esac
        case "$line" in [A-Z_]*=*) ;; *) continue ;; esac
        key="${line%%=*}"
        val="${line#*=}"
        case "$val" in \"*\") val="${val#\"}"; val="${val%\"}" ;; \'*\') val="${val#\'}"; val="${val%\'}" ;; esac
        export "$key=$val"
    done < "$ENV_FILE"
else
    echo "❌ .env не найден: $ENV_FILE"
    exit 1
fi

VPS_USER="${VPS_USER:-root}"
VPS_IP="${VPS_HOST:-${VPS_IP:-}}"
VPS_PASS="${VPS_PASS:-}"
SSH_KEY="${VPS_SSH_KEY:-}"
VPS_DIR="${VPS_DIR:-/opt/levitan/projects/ai-eggs}"
VENV_DIR="${VENV_DIR:-.server_venv}"
ECOSYSTEM_ROOT="${ECOSYSTEM_ROOT:-/opt/levitan}"
LOCAL_DIR="${SCRIPT_DIR}/.."

if [ -z "$VPS_IP" ]; then
    echo "❌ VPS_HOST/VPS_IP не задан в .env"
    exit 1
fi

echo "🚀 DEPLOY ANGELA → VPS ($VPS_IP)"
echo "   Удалённый путь: $VPS_DIR"
echo "   venv: $VENV_DIR"
echo "================================"

# --- Базовые SSH-опции ---
SSH_BASE_OPTS="-o ConnectTimeout=10 -o StrictHostKeyChecking=no"
if [ -n "$SSH_KEY" ] && [ -f "$SSH_KEY" ]; then
    SSH_BASE_OPTS="$SSH_BASE_OPTS -i $SSH_KEY"
fi

# --- ШАГ 0: Проверяем SSH-доступ ---
echo ""
echo "🔌 ШАГ 0: Проверяем доступность сервера..."
ssh $SSH_BASE_OPTS -o BatchMode=yes "${VPS_USER}@${VPS_IP}" "echo OK" > /dev/null 2>&1

if [ $? -ne 0 ]; then
    echo "⚠️  SSH-ключ не настроен или сервер недоступен."
    if [ -n "$VPS_PASS" ] && command -v sshpass >/dev/null 2>&1; then
        echo "   Пробую через sshpass..."
        SSH_OPTS="$SSH_BASE_OPTS"
        SSH_WRAPPER="sshpass -p $VPS_PASS ssh $SSH_BASE_OPTS"
        RSYNC_E="sshpass -p $VPS_PASS ssh $SSH_BASE_OPTS"
        ssh $SSH_WRAPPER "echo OK" > /dev/null 2>&1 || { echo "❌ Сервер $VPS_IP недоступен!"; exit 1; }
    else
        echo "   Пробую подключиться с запросом пароля..."
        SSH_OPTS="$SSH_BASE_OPTS"
        SSH_WRAPPER="ssh $SSH_BASE_OPTS"
        RSYNC_E="ssh $SSH_BASE_OPTS"
        ssh $SSH_BASE_OPTS "${VPS_USER}@${VPS_IP}" "echo OK" > /dev/null 2>&1 || {
            echo "❌ Сервер ${VPS_IP} недоступен! Проверь IP/пароль/файрвол."
            echo "   Сначала: bash setup_ssh_key.sh"
            exit 1
        }
    fi
else
    SSH_OPTS="$SSH_BASE_OPTS"
    SSH_WRAPPER="ssh $SSH_BASE_OPTS -o BatchMode=yes"
    RSYNC_E="ssh $SSH_BASE_OPTS -o BatchMode=yes"
fi
echo "✅ Сервер доступен"

# --- ШАГ 1: Синхронизируем код агента ---
echo ""
echo "📁 ШАГ 1: Синхронизируем код агента..."
rsync -avz --progress -e "$RSYNC_E" \
    --exclude='venv/' \
    --exclude='.server_venv/' \
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
rsync -avz --progress -e "$RSYNC_E" \
    "${LOCAL_DIR}/.env" \
    "${VPS_USER}@${VPS_IP}:${VPS_DIR}/.env"

rsync -avz --progress -e "$RSYNC_E" \
    --exclude='bitrix_scans/' \
    --exclude='sandbox_scans/' \
    --exclude='daily_reports/' \
    "${LOCAL_DIR}/data/" \
    "${VPS_USER}@${VPS_IP}:${VPS_DIR}/data/"

# --- ШАГ 3: Синхронизируем requirements ---
echo ""
echo "📦 ШАГ 3: Синхронизируем requirements.txt..."
rsync -avz -e "$RSYNC_E" \
    "${LOCAL_DIR}/requirements.txt" \
    "${VPS_USER}@${VPS_IP}:${VPS_DIR}/requirements.txt" 2>/dev/null

# --- ШАГ 4: Настраиваем PM2 + venv на VPS ---
echo ""
echo "♻️  ШАГ 4: Настраиваем PM2 + venv на VPS..."
ssh $SSH_WRAPPER "${VPS_USER}@${VPS_IP}" "VPS_DIR='$VPS_DIR' VENV_DIR='$VENV_DIR' ECOSYSTEM_ROOT='$ECOSYSTEM_ROOT' bash -s" << 'REMOTE_SETUP'
    set -e
    echo "--- Настройка на VPS ---"
    cd "$VPS_DIR/"

    # Создаём venv если нет
    if [ ! -d "$VENV_DIR" ]; then
        echo "🐍 Создаём venv ($VENV_DIR)..."
        python3 -m venv "$VENV_DIR"
    fi

    # Устанавливаем зависимости
    echo "📦 Устанавливаем зависимости..."
    "$VENV_DIR/bin/pip" install -q python-dotenv requests httpx edge-tts 2>/dev/null || true
    if [ -f "requirements.txt" ]; then
        "$VENV_DIR/bin/pip" install -q -r requirements.txt 2>/dev/null || true
    fi

    cd agent/

    # Убиваем старые scheduler процессы
    pm2 delete angela-scheduler 2>/dev/null || true

    # Проверяем есть ли ecosystem.config.js
    if [ -f "ecosystem.config.js" ]; then
        cp ecosystem.config.js ecosystem.config.cjs
        echo "⚙️  Запуск через ecosystem.config.cjs..."
        pm2 start ecosystem.config.cjs 2>/dev/null || pm2 restart ecosystem.config.cjs
    else
        echo "⚙️  Запуск через CLI..."
        pm2 start scheduler.py \
            --name angela-scheduler \
            --interpreter "$VPS_DIR/$VENV_DIR/bin/python3" \
            --cwd "$VPS_DIR/agent/" \
            --
    fi

    # Перезапускаем angela-bot и angela-autopilot
    pm2 restart angela-bot 2>/dev/null || echo "ℹ️  angela-bot: запускаем через ecosystem"
    pm2 restart angela-autopilot 2>/dev/null || echo "ℹ️  angela-autopilot: уже в ecosystem"

    # Также перезапускаем корневой ecosystem (ptenchikova, angela-server, vezem-web)
    if [ -f "$ECOSYSTEM_ROOT/ecosystem.config.cjs" ]; then
        pm2 start "$ECOSYSTEM_ROOT/ecosystem.config.cjs" 2>/dev/null || pm2 restart "$ECOSYSTEM_ROOT/ecosystem.config.cjs"
    fi

    pm2 save

    echo ""
    echo "📋 PM2 STATUS:"
    pm2 list
REMOTE_SETUP

# --- ШАГ 5: Настраиваем CRON как FALLBACK ---
echo ""
echo "⏰ ШАГ 5: Настраиваем cron-watchdog + fallback на VPS..."
ssh $SSH_WRAPPER "${VPS_USER}@${VPS_IP}" "VPS_DIR='$VPS_DIR' VENV_DIR='$VENV_DIR' bash -s" << 'CRONEOF'
    set -e
    VENV_PYTHON="$VPS_DIR/$VENV_DIR/bin/python3"
    REPORTER="$VPS_DIR/agent/daily_report.py"
    CALL_QUALITY="$VPS_DIR/agent/call_quality_report.py"
    LOG_DIR="$VPS_DIR/agent/logs"
    HEARTBEAT="$VPS_DIR/agent/logs/scheduler_heartbeat.json"
    WATCHDOG="$VPS_DIR/agent/watchdog_cron.sh"

    mkdir -p "$LOG_DIR"

    # Создаём watchdog скрипт
    cat > "$WATCHDOG" << WD
#!/bin/bash
# Watchdog — перезапускает scheduler если heartbeat устарел
HEARTBEAT="$HEARTBEAT"

if [ ! -f "\$HEARTBEAT" ]; then
    echo "[\$(date)] WATCHDOG: heartbeat не найден, перезапускаю scheduler"
    pm2 restart angela-scheduler 2>/dev/null
    exit 0
fi

# Проверяем возраст heartbeat файла (> 600 секунд = 10 минут)
HEARTBEAT_AGE=\$(( \$(date +%s) - \$(stat -c %Y "\$HEARTBEAT" 2>/dev/null || stat -f %m "\$HEARTBEAT" 2>/dev/null || echo 0) ))
if [ "\$HEARTBEAT_AGE" -gt 600 ]; then
    echo "[\$(date)] WATCHDOG: heartbeat устарел (\${HEARTBEAT_AGE}с), перезапускаю scheduler"
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
     echo "# health_monitor ОТКЛЮЧЁН") | crontab -

    echo "✅ Cron настроен:"
    crontab -l
CRONEOF

# --- ШАГ 6: Проверяем здоровье ---
echo ""
echo "🔍 ШАГ 6: Финальная проверка..."
ssh $SSH_WRAPPER "${VPS_USER}@${VPS_IP}" "VPS_DIR='$VPS_DIR' bash -s" << 'CHECK'
    echo "--- PM2 ---"
    pm2 list
    echo ""
    echo "--- Heartbeat ---"
    cat "$VPS_DIR/agent/logs/scheduler_heartbeat.json" 2>/dev/null || echo "(пока нет, подождите минуту)"
    echo ""
    echo "--- Scheduler log (последние 5 строк) ---"
    tail -5 "$VPS_DIR/agent/logs/scheduler.log" 2>/dev/null || echo "(пока пусто)"
CHECK

echo ""
echo "================================"
echo "✅ ДЕПЛОЙ ЗАВЕРШЁН!"
echo "   Ангела на VPS ($VPS_IP) теперь:"
echo "   1. scheduler.py под PM2 с heartbeat"
echo "   2. Cron-watchdog перезапускает scheduler если он умер"
echo "   3. Cron-fallback отчёт в 20:10 (страховка)"
echo "   4. Retry-логика: 3 попытки отправки отчёта"
echo ""
echo "📊 Проверь через 2 минуты:"
echo "   ssh -i ${SSH_KEY:-<key>} ${VPS_USER}@${VPS_IP} 'cat ${VPS_DIR}/agent/logs/scheduler_heartbeat.json'"
echo "================================"
