#!/bin/bash

# ============================================================
# Управление Анжелочкой v2 — с защитой от дублей и PID-файлами
# ============================================================

PROJECT_DIR="/Users/igorvasin/freelance-2026/ai-eggs"
AGENT_DIR="$PROJECT_DIR/agent"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python3"
LOG_DIR="$AGENT_DIR/logs"
PID_FILE_BOT="$LOG_DIR/bot.pid"
PID_FILE_SERVER="$LOG_DIR/server.pid"
PID_FILE_AUTOPILOT="$LOG_DIR/autopilot.pid"

mkdir -p "$LOG_DIR"

# --- Убить процессы безопасно ---
cleanup() {
    echo "🧹 Завершение всех процессов Анжелы..."
    
    # Убиваем по PID-файлам (точечно)
    for pidfile in "$PID_FILE_BOT" "$PID_FILE_SERVER"; do
        if [ -f "$pidfile" ]; then
            PID=$(cat "$pidfile")
            if kill -0 "$PID" 2>/dev/null; then
                echo "   Убиваю PID $PID (из $pidfile)"
                kill -9 "$PID" 2>/dev/null
            fi
            rm -f "$pidfile"
        fi
    done
    
    # Страховка: убиваем по имени файла (на случай orphaned процессов)
    pkill -9 -f "tg_bot.py" 2>/dev/null
    pkill -9 -f "ai-eggs/agent/server.py" 2>/dev/null
    pkill -9 -f "scheduler.py" 2>/dev/null
    
    sleep 1
    echo "✅ Все процессы остановлены."
}

case "$1" in
    start)
        cleanup
        echo ""
        echo "🚀 Запуск Анжелы..."
        cd "$AGENT_DIR"
        
        # Запуск бота (единственный инстанс)
        nohup "$VENV_PYTHON" -u tg_bot.py >> "$LOG_DIR/bot.log" 2>&1 &
        echo $! > "$PID_FILE_BOT"
        echo "   Бот: PID $(cat $PID_FILE_BOT) → logs/bot.log"
        
        # Запуск API-сервера
        nohup "$VENV_PYTHON" -u server.py >> "$LOG_DIR/server.log" 2>&1 &
        echo $! > "$PID_FILE_SERVER"
        echo "   Сервер: PID $(cat $PID_FILE_SERVER) → logs/server.log"
        
        # Запуск Автопилота (Routine Engine)
        nohup "$VENV_PYTHON" -u autopilot.py >> "$LOG_DIR/autopilot.log" 2>&1 &
        echo $! > "$PID_FILE_AUTOPILOT"
        echo "   Автопилот: PID $(cat $PID_FILE_AUTOPILOT) → logs/autopilot.log"
        echo "   📅 Отчеты: 09:00 и 21:00"
        
        echo ""
        echo "====================================="
        echo "🐣 Анжела работает автономно!"
        echo "   Можно закрыть терминал."
        echo "   Проверка: $0 status"
        echo "====================================="
        ;;
    stop)
        cleanup
        ;;
    restart)
        echo "🔄 Перезапуск Анжелы..."
        cleanup
        sleep 1
        exec "$0" start
        ;;
    status)
        echo "📊 Статус Анжелы:"
        echo ""
        
        # Бот
        if [ -f "$PID_FILE_BOT" ]; then
            PID=$(cat "$PID_FILE_BOT")
            if pgrep -F "$PID_FILE_BOT" >/dev/null 2>&1; then
                echo "   🟢 Бот: РАБОТАЕТ (PID: $PID)"
            else
                echo "   🔴 Бот: УПАЛ (PID $PID мёртв)"
            fi
        else
            echo "   🔴 Бот: ОСТАНОВЛЕН (нет PID-файла)"
        fi
        
        # Сервер
        if [ -f "$PID_FILE_SERVER" ]; then
            PID=$(cat "$PID_FILE_SERVER")
            if pgrep -F "$PID_FILE_SERVER" >/dev/null 2>&1; then
                echo "   🟢 Сервер: РАБОТАЕТ (PID: $PID)"
            else
                echo "   🔴 Сервер: УПАЛ (PID $PID мёртв)"
            fi
        else
            echo "   🔴 Сервер: ОСТАНОВЛЕН (нет PID-файла)"
        fi
        
        echo ""
        echo "   Последние 5 строк лога бота:"
        tail -5 "$LOG_DIR/bot.log" 2>/dev/null | sed 's/^/   │ /'
        
        # Автопилот
        if [ -f "$PID_FILE_AUTOPILOT" ]; then
            PID=$(cat "$PID_FILE_AUTOPILOT")
            if kill -0 "$PID" 2>/dev/null; then
                echo "   🟢 Автопилот: РАБОТАЕТ (PID: $PID)"
                echo "      📅 Отчеты: 09:00 и 21:00"
            else
                echo "   🔴 Автопилот: УПАЛ (PID $PID мёртв)"
            fi
        else
            echo "   🔴 Автопилот: ОСТАНОВЛЕН"
        fi
        ;;
    logs)
        echo "📋 Логи бота (последние 30 строк):"
        echo "─────────────────────────────────"
        tail -30 "$LOG_DIR/bot.log" 2>/dev/null
        echo ""
        echo "📋 Логи сервера (последние 15 строк):"
        echo "─────────────────────────────────"
        tail -15 "$LOG_DIR/server.log" 2>/dev/null
        ;;
    *)
        echo "Использование: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac
