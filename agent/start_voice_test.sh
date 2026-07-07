#!/bin/bash
# start_voice_test.sh — запуск тестового звонка Voice Angela
# Использование: bash agent/start_voice_test.sh
# Mango позвонит на указанный номер и соединит с baresip.
# Ответь на звонок — поговоришь с Анжелой (голос Kore).

PHONE="${1:-+78612025110}"

cd /root/antigravity/ai-eggs

echo "=== Voice Angela Test ==="
echo "Calling $PHONE ..."
echo "Ответь на звонок и говори с Анжелой!"
echo ""

# Run the test script
timeout 90 python3 agent/test_voice_call.py --phone "$PHONE"
