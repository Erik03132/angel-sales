#!/bin/bash
# ============================================================
# 🛑 ЭКСТРЕННАЯ ОСТАНОВКА АНЖЕЛОЧКИ
# Убивает ВСЕ процессы и ставит kill switch.
# Использование: bash stop_angela.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"

echo "🛑 ЭКСТРЕННАЯ ОСТАНОВКА АНЖЕЛОЧКИ"
echo "================================="

# 1. Ставим kill switch (оба уровня)
touch "${LOG_DIR}/STOP_BOT" 2>/dev/null
touch "${PROJECT_DIR}/STOP_BOT" 2>/dev/null
echo "✅ Kill switches установлены"

# 2. Убиваем процессы по имени
pkill -9 -f "bitrix_bot" 2>/dev/null && echo "✅ bitrix_bot убит" || echo "   bitrix_bot не найден"
pkill -9 -f "scheduler.py" 2>/dev/null && echo "✅ scheduler убит" || echo "   scheduler не найден"
pkill -9 -f "tg_bot" 2>/dev/null && echo "✅ tg_bot убит" || echo "   tg_bot не найден"
pkill -9 -f "proactive_engine" 2>/dev/null && echo "✅ proactive_engine убит" || echo "   proactive_engine не найден"

# 3. Убиваем по PID из файлов
for pidfile in "${LOG_DIR}"/*.pid; do
    if [ -f "$pidfile" ]; then
        pid=$(cat "$pidfile" 2>/dev/null)
        if [ -n "$pid" ]; then
            kill -9 "$pid" 2>/dev/null && echo "✅ PID $pid убит (из $pidfile)"
        fi
        rm -f "$pidfile"
    fi
done

# 4. Чистим lock-файлы
rm -f "${LOG_DIR}/bitrix_bot.lock" 2>/dev/null
echo "✅ Lock-файлы очищены"

# 5. Проверяем
sleep 1
remaining=$(pgrep -f "bitrix_bot|scheduler|tg_bot|proactive_engine" 2>/dev/null | wc -l | tr -d ' ')
if [ "$remaining" -eq 0 ]; then
    echo ""
    echo "🎉 ВСЕ ПРОЦЕССЫ АНЖЕЛОЧКИ ОСТАНОВЛЕНЫ!"
else
    echo ""
    echo "⚠️  Осталось $remaining процессов. Попробуйте:"
    echo "   killall -9 Python"
    pgrep -lf "bitrix_bot|scheduler|tg_bot" 2>/dev/null
fi

echo ""
echo "Для перезапуска удалите STOP_BOT:"
echo "   rm ${LOG_DIR}/STOP_BOT ${PROJECT_DIR}/STOP_BOT"
