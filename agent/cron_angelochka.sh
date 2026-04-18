#!/bin/bash
# Cron-скрипт для Анжелочки: сканирование Bitrix24 и ежедневный отчёт
#
# Установка в crontab:
#   crontab -e
#   Добавить строки:
#   0 8,11,14,17 * * * /Users/igorvasin/freelance-2026/ai-eggs/agent/cron_angelochka.sh scan
#   0 20 * * * /Users/igorvasin/freelance-2026/ai-eggs/agent/cron_angelochka.sh report

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="/Users/igorvasin/freelance-2026/ai-eggs/venv/bin/python3"
LOG_DIR="${SCRIPT_DIR}/logs"
mkdir -p "${LOG_DIR}"

case "$1" in
    scan)
        echo "[$(date)] Запуск сканирования Bitrix24..." >> "${LOG_DIR}/cron.log"
        ${VENV} "${SCRIPT_DIR}/bitrix_scanner.py" >> "${LOG_DIR}/scanner.log" 2>&1
        ${VENV} "${SCRIPT_DIR}/sync_products.py" >> "${LOG_DIR}/scanner.log" 2>&1
        echo "[$(date)] Сканирование завершено." >> "${LOG_DIR}/cron.log"
        ;;
    report)
        echo "[$(date)] Запуск ежедневного отчёта..." >> "${LOG_DIR}/cron.log"
        # Сначала свежий скан
        ${VENV} "${SCRIPT_DIR}/bitrix_scanner.py" >> "${LOG_DIR}/scanner.log" 2>&1
        # Потом отчёт
        ${VENV} "${SCRIPT_DIR}/daily_report.py" >> "${LOG_DIR}/report.log" 2>&1
        echo "[$(date)] Отчёт отправлен." >> "${LOG_DIR}/cron.log"
        ;;
    *)
        echo "Usage: $0 {scan|report}"
        echo "  scan   — сканировать Bitrix24 (каждые 3 часа)"
        echo "  report — отчёт Андрею в Telegram (в 20:00)"
        exit 1
        ;;
esac
