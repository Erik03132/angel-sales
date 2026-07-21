#!/bin/bash
# =======================================================
# SETUP SSH KEY — Настройка ключевого доступа к VPS
# После выполнения sshpass БОЛЬШЕ НЕ НУЖЕН!
#
# Конфиг читается из ../.env (VPS_HOST, VPS_USER, VPS_PASS, VPS_SSH_KEY)
# =======================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env"

# --- Безопасное чтение .env (не интерпретирует & ! $ и т.п.) ---
if [ -f "$ENV_FILE" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        # Пропускаем пустые строки и комментарии
        case "$line" in ''|\#*) continue ;; esac
        # Только KEY=VALUE (KEY = A-Z_)
        case "$line" in [A-Z_]*=*) ;; *) continue ;; esac
        key="${line%%=*}"
        val="${line#*=}"
        # Снимаем внешние кавычки если есть
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
KEY_FILE="${VPS_SSH_KEY:-$HOME/.ssh/id_ed25519}"

if [ -z "$VPS_IP" ]; then
    echo "❌ VPS_HOST/VPS_IP не задан в .env"
    exit 1
fi

echo "🔑 НАСТРОЙКА SSH-КЛЮЧА → VPS ($VPS_IP)"
echo "================================"
echo "   Ключ: $KEY_FILE"

# Шаг 1: Генерируем ключ если нет
if [ ! -f "$KEY_FILE" ]; then
    echo "📝 Генерируем SSH-ключ (ed25519)..."
    mkdir -p "$(dirname "$KEY_FILE")"
    ssh-keygen -t ed25519 -f "$KEY_FILE" -N "" -q
    echo "✅ Ключ создан: $KEY_FILE"
else
    echo "✅ SSH-ключ уже есть: $KEY_FILE"
fi

# Шаг 2: Копируем на сервер
echo ""
echo "📤 Копируем ключ на сервер..."

# Пробуем через ssh-copy-id (запросит пароль)
if [ -n "$VPS_PASS" ] && command -v sshpass >/dev/null 2>&1; then
    sshpass -p "$VPS_PASS" ssh-copy-id -i "$KEY_FILE" -o StrictHostKeyChecking=no "${VPS_USER}@${VPS_IP}"
else
    echo "⚠️  Введи пароль VPS когда попросит: $VPS_PASS"
    echo ""
    ssh-copy-id -i "$KEY_FILE" -o StrictHostKeyChecking=no "${VPS_USER}@${VPS_IP}"
fi

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ SSH-ключ установлен! Проверяем вход без пароля..."
    if ssh -i "$KEY_FILE" -o BatchMode=yes -o StrictHostKeyChecking=no "${VPS_USER}@${VPS_IP}" "echo OK" 2>/dev/null | grep -q OK; then
        echo "✅ Вход по ключу работает: ssh -i $KEY_FILE ${VPS_USER}@${VPS_IP}"
        echo ""
        echo "🚀 Теперь запусти деплой:"
        echo "   bash deploy_to_vps.sh"
    else
        echo "⚠️  Ключ скопирован, но вход без пароля не прошёл. Проверь authorized_keys на VPS."
    fi
else
    echo ""
    echo "❌ Не удалось скопировать ключ. Попробуй вручную:"
    echo "   cat ${KEY_FILE}.pub | ssh ${VPS_USER}@${VPS_IP} 'mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys'"
fi
