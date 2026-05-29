#!/bin/bash
# =======================================================
# SETUP SSH KEY — Настройка ключевого доступа к VPS
# После выполнения sshpass БОЛЬШЕ НЕ НУЖЕН!
# =======================================================

VPS_USER="root"
VPS_IP="72.56.38.19"
KEY_FILE="$HOME/.ssh/id_ed25519"

echo "🔑 НАСТРОЙКА SSH-КЛЮЧА → VPS ($VPS_IP)"
echo "================================"

# Шаг 1: Генерируем ключ если нет
if [ ! -f "$KEY_FILE" ]; then
    echo "📝 Генерируем SSH-ключ (ed25519)..."
    ssh-keygen -t ed25519 -f "$KEY_FILE" -N "" -q
    echo "✅ Ключ создан: $KEY_FILE"
else
    echo "✅ SSH-ключ уже есть: $KEY_FILE"
fi

# Шаг 2: Копируем на сервер
echo ""
echo "📤 Копируем ключ на сервер..."
echo "⚠️  Введи пароль VPS когда попросит: zE4qDJb-+Y+rv+"
echo ""

ssh-copy-id -i "$KEY_FILE" -o StrictHostKeyChecking=no "${VPS_USER}@${VPS_IP}"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ SSH-ключ установлен! Теперь можно подключаться без пароля:"
    echo "   ssh root@72.56.38.19"
    echo ""
    echo "🚀 Теперь запусти деплой:"
    echo "   bash deploy_to_vps.sh"
else
    echo ""
    echo "❌ Не удалось скопировать ключ. Попробуй вручную:"
    echo "   cat ~/.ssh/id_ed25519.pub | ssh root@72.56.38.19 'mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys'"
fi
