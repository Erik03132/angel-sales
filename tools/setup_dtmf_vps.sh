#!/bin/bash
# ============================================================
# 🔧 Настройка DTMF на VPS (72.56.38.19)
# Запуск: bash setup_dtmf_vps.sh
# ============================================================

set -e

VPS="root@72.56.38.19"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_DIR="$SCRIPT_DIR/../agent"

echo "📦 1. Загружаю dtmf_handler.py на VPS..."
scp -o ConnectTimeout=20 "$AGENT_DIR/dtmf_handler.py" "$VPS:/opt/dtmf_handler.py"

echo "📦 2. Загружаю .env на VPS..."
scp -o ConnectTimeout=20 "$SCRIPT_DIR/../.env" "$VPS:/opt/.env"

echo "🔧 3. Обновляю baresip конфиг для DTMF..."
ssh -o ConnectTimeout=20 "$VPS" 'cat > /root/.baresip/config << '\''CONF'\''
# Baresip config для Mango Office SIP-бота + DTMF
module_path             /usr/lib/baresip/modules

# Аудио — без реального звукового устройства (VPS)
audio_player            aufile,/tmp/mango_play.wav
audio_source            aufile,/tmp/mango_play.wav

# Кодеки
audio_codecs            PCMA/8000/1,PCMU/8000/1

# SIP
sip_listen              0.0.0.0:5060

# Авто-ответ на входящие
auto_answer             yes
auto_answer_delay       0

# Модули
module                  uuid.so
module                  aufile.so

# DTMF через SIP INFO (RFC 2833)
module                  dtmfio.so

# HTTP-контроль (для управления из скриптов)
#module                  httpreq.so
CONF
'

echo "🔄 4. Перезапускаю baresip..."
ssh -o ConnectTimeout=20 "$VPS" '
    screen -S sip_bot -X quit 2>/dev/null || true
    sleep 1
    pkill baresip 2>/dev/null || true
    sleep 1
    screen -dmS sip_bot baresip -f /root/.baresip -v
    sleep 3
    screen -S sip_bot -X hardcopy /tmp/bs_check.txt
    echo "=== Baresip status ==="
    cat /tmp/bs_check.txt | tail -5
'

echo "🚀 5. Запускаю DTMF Handler в PM2..."
ssh -o ConnectTimeout=20 "$VPS" '
    # Останавливаем старый если есть
    pm2 delete dtmf-handler 2>/dev/null || true
    
    # Запускаем
    pm2 start /opt/dtmf_handler.py \
        --name dtmf-handler \
        --interpreter python3 \
        -- --mode http --port 8086
    
    sleep 2
    pm2 list | grep -E "dtmf|mango"
    
    echo ""
    echo "=== Test DTMF Handler ==="
    curl -s http://localhost:8086/ 2>/dev/null
'

echo ""
echo "✅ Готово! DTMF Handler на порту 8086"
echo "   Тест: curl -X POST http://72.56.38.19:8086/ -d '{\"digit\":\"1\",\"call_id\":\"test\",\"phone\":\"+79859234644\"}'"
