#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# 🛡️ RESURRECT.SH — Полное восстановление всей инфраструктуры
# ═══════════════════════════════════════════════════════════════
# Запускается:
#   1. Вручную: ssh root@VPS 'bash /root/antigravity/resurrect.sh'
#   2. Кроном (Level 3): каждые 5 минут если что-то упало
#   3. Auto-heal из health_monitor.py как последний рубеж
# ═══════════════════════════════════════════════════════════════

set -uo pipefail

BASE="/root/antigravity"
AGENT="$BASE/ai-eggs/agent"
LOG="$BASE/logs/resurrect.log"
VENV="$BASE/angel-backend/.venv/bin/python"

mkdir -p "$BASE/logs"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $1" | tee -a "$LOG"; }

log "=============================="
log "🛡️ RESURRECT START"

# ── Шаг 1: PM2 живой? ──────────────────────────────────────────
if ! pm2 list &>/dev/null; then
    log "❌ PM2 не отвечает! Перезапускаем PM2..."
    pm2 kill 2>/dev/null || true
    sleep 2
    pm2 list &>/dev/null || { log "FATAL: PM2 не стартует"; exit 1; }
fi

# ── Шаг 2: Создаём .cjs если их нет (защита от ES-module бага) ──
for eco in "$BASE/ecosystem.config.js" "$AGENT/ecosystem.config.js"; do
    cjs="${eco%.js}.cjs"
    if [ -f "$eco" ] && [ ! -f "$cjs" ]; then
        cp "$eco" "$cjs"
        log "📋 Создал $cjs"
    fi
done

# ── Шаг 3: Запускаем оба ecosystem ─────────────────────────────
STARTED=0
for eco in "$BASE/ecosystem.config.cjs" "$AGENT/ecosystem.config.cjs"; do
    if [ -f "$eco" ]; then
        pm2 start "$eco" 2>&1 | tee -a "$LOG"
        STARTED=$((STARTED + 1))
        log "✅ Запущено из: $eco"
    fi
done

if [ "$STARTED" -eq 0 ]; then
    log "⚠️ Ecosystem файлов не найдено. Пробуем pm2 resurrect..."
    pm2 resurrect 2>&1 | tee -a "$LOG" || true
fi

# ── Шаг 4: Проверяем статус ────────────────────────────────────
sleep 5
log "📋 Статус PM2:"
pm2 list 2>&1 | tee -a "$LOG"

# ── Шаг 5: Считаем не-online процессы ─────────────────────────
OFFLINE=$(pm2 jlist 2>/dev/null | python3 -c "
import sys, json
procs = json.load(sys.stdin)
bad = [p['name'] for p in procs if p.get('pm2_env', {}).get('status') != 'online']
print(len(bad))
print('\n'.join(bad))
" 2>/dev/null || echo "0")

COUNT=$(echo "$OFFLINE" | head -1)
NAMES=$(echo "$OFFLINE" | tail -n +2)

if [ "$COUNT" -gt 0 ] 2>/dev/null; then
    log "⚠️ Offline процессы ($COUNT): $NAMES"
else
    log "✅ ВСЕ ПРОЦЕССЫ ONLINE"
fi

# ── Шаг 6: pm2 save ────────────────────────────────────────────
pm2 save --force 2>&1 | tee -a "$LOG"
log "💾 pm2 dump сохранён"

log "🛡️ RESURRECT DONE"
log "=============================="
