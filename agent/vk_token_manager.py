#!/usr/bin/env python3
"""
VK Token Manager — Получение и автообновление User Token для market.* методов.

Два режима:
  1. --auth  → Генерирует URL для авторизации (один раз, в браузере)
  2. --exchange CODE → Обменивает code на access_token (запуск на VPS!)
  3. --check → Проверяет текущий токен

ВАЖНО: --exchange нужно запускать НА VPS, чтобы токен был привязан к его IP.

Использование:
  # Шаг 1 (на любой машине): Получить auth URL
  python3 vk_token_manager.py --auth

  # Шаг 2 (открыть URL в браузере, авторизоваться, скопировать code из redirect)

  # Шаг 3 (НА VPS!): Обменять code на токен
  python3 vk_token_manager.py --exchange CODE_FROM_REDIRECT

  # Проверка:
  python3 vk_token_manager.py --check
"""

import argparse
import json
import os
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, '.env')

# ═══════════════════════════════════════════════
# Конфигурация VK App
# ═══════════════════════════════════════════════

# Standalone-приложение ВезёмЦыплят
VK_APP_ID = '54572099'

# Секретный ключ приложения (из настроек app на vk.com/dev)
# Нужен для Authorization Code Flow
VK_APP_SECRET = os.getenv('VK_APP_SECRET', '')

# Redirect URI для Standalone-приложения
REDIRECT_URI = 'https://oauth.vk.com/blank.html'

# Права доступа для market.* методов (строковые имена — новый формат VK API)
SCOPE = 'market,photos,groups,wall,offline'

VK_API_VERSION = '5.199'


# ═══════════════════════════════════════════════
# Утилиты .env
# ═══════════════════════════════════════════════

def read_env():
    """Читает .env в dict."""
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, _, v = line.partition('=')
                    env[k.strip()] = v.strip()
    return env


def update_env_var(key, value):
    """Обновляет или добавляет переменную в .env (атомарно)."""
    lines = []
    found = False
    
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, 'r') as f:
            lines = f.readlines()
    
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f'{key}='):
            new_lines.append(f'{key}={value}\n')
            found = True
        else:
            new_lines.append(line)
    
    if not found:
        new_lines.append(f'{key}={value}\n')
    
    with open(ENV_PATH, 'w') as f:
        f.writelines(new_lines)
    
    # Также установить в текущий os.environ
    os.environ[key] = value


# ═══════════════════════════════════════════════
# Шаг 1: Генерация Auth URL
# ═══════════════════════════════════════════════

def generate_auth_url():
    """Генерирует URL для авторизации через Implicit Flow."""
    
    # Implicit Flow (для Standalone — токен прямо в URL)
    implicit_url = (
        f"https://oauth.vk.com/authorize?"
        f"client_id={VK_APP_ID}"
        f"&display=page"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope={SCOPE}"
        f"&response_type=token"
        f"&v={VK_API_VERSION}"
    )
    
    # Authorization Code Flow (если есть APP_SECRET)
    code_url = (
        f"https://oauth.vk.com/authorize?"
        f"client_id={VK_APP_ID}"
        f"&display=page"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope={SCOPE}"
        f"&response_type=code"
        f"&v={VK_API_VERSION}"
    )
    
    print("=" * 60)
    print("🔑 VK Token Manager — Авторизация")
    print("=" * 60)
    print()
    print("📌 ВАРИАНТ 1 — Implicit Flow (простой, токен в URL)")
    print("   Токен привязывается к IP, с которого открыт URL.")
    print("   Живёт до отзыва (offline scope).")
    print()
    print(f"   👉 {implicit_url}")
    print()
    print("   После авторизации скопируй access_token из URL в адресной строке.")
    print("   URL будет вида:")
    print("   https://oauth.vk.com/blank.html#access_token=vk1.a.XXXXX&...")
    print()
    print("-" * 60)
    print()
    print("📌 ВАРИАНТ 2 — Code Flow (через VPS, без IP-привязки)")
    print("   Требует VK_APP_SECRET в .env")
    print()
    print(f"   👉 {code_url}")
    print()
    print("   После авторизации скопируй CODE из URL:")
    print("   https://oauth.vk.com/blank.html?code=XXXXXXXX")
    print()
    print("   Затем НА VPS запусти:")
    print("   python3 vk_token_manager.py --exchange CODE")
    print()
    print("=" * 60)
    
    return implicit_url


# ═══════════════════════════════════════════════
# Шаг 2: Обмен code → token (Code Flow)
# ═══════════════════════════════════════════════

def exchange_code(code):
    """Обменивает authorization code на access_token.
    ЗАПУСКАТЬ НА VPS — токен привязывается к IP сервера."""
    
    env = read_env()
    app_secret = env.get('VK_APP_SECRET', '') or VK_APP_SECRET
    
    if not app_secret:
        print("❌ VK_APP_SECRET не найден!")
        print("   Добавь в .env: VK_APP_SECRET=xxxxx")
        print("   Секрет приложения: vk.com/dev → Приложение → Настройки → Защищённый ключ")
        return None
    
    url = (
        f"https://oauth.vk.com/access_token?"
        f"client_id={VK_APP_ID}"
        f"&client_secret={app_secret}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&code={code}"
    )
    
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"❌ Ошибка запроса: {e}")
        return None
    
    if 'error' in data:
        print(f"❌ VK Error: {data.get('error_description', data.get('error'))}")
        return None
    
    token = data.get('access_token')
    user_id = data.get('user_id')
    expires = data.get('expires_in', 0)
    
    if not token:
        print(f"❌ Токен не получен: {data}")
        return None
    
    # Сохраняем в .env
    update_env_var('VK_USER_TOKEN', token)
    
    print("=" * 60)
    print("✅ Токен получен!")
    print(f"   User ID: {user_id}")
    print(f"   Token: {token[:30]}...{token[-10:]}")
    print(f"   Expires: {'never (offline)' if expires == 0 else f'{expires}s'}")
    print(f"   Сохранён в: {ENV_PATH}")
    print("=" * 60)
    
    return token


# ═══════════════════════════════════════════════
# Сохранение токена из Implicit Flow
# ═══════════════════════════════════════════════

def save_token(token):
    """Сохраняет токен, полученный через Implicit Flow."""
    update_env_var('VK_USER_TOKEN', token)
    
    # Проверяем токен
    check_token_internal(token)


# ═══════════════════════════════════════════════
# Проверка токена
# ═══════════════════════════════════════════════

def check_token_internal(token):
    """Проверяет валидность токена."""
    url = (
        f"https://api.vk.com/method/users.get?"
        f"access_token={token}"
        f"&v={VK_API_VERSION}"
    )
    
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"❌ Ошибка проверки: {e}")
        return False
    
    if 'error' in data:
        err = data['error']
        print(f"❌ Токен невалиден: [{err.get('error_code')}] {err.get('error_msg')}")
        return False
    
    users = data.get('response', [])
    if users:
        u = users[0]
        print(f"✅ Токен валиден: {u.get('first_name')} {u.get('last_name')} (id{u.get('id')})")
        
        # Проверяем market scope
        url2 = (
            f"https://api.vk.com/method/market.get?"
            f"owner_id=-238316002"
            f"&count=1"
            f"&access_token={token}"
            f"&v={VK_API_VERSION}"
        )
        try:
            req2 = urllib.request.Request(url2)
            with urllib.request.urlopen(req2, timeout=10) as resp2:
                data2 = json.loads(resp2.read().decode('utf-8'))
            if 'error' in data2:
                err2 = data2['error']
                print(f"⚠️ market.get: [{err2.get('error_code')}] {err2.get('error_msg')}")
            else:
                count = data2.get('response', {}).get('count', 0)
                print(f"✅ market.get: {count} товаров в магазине")
        except Exception as e:
            print(f"⚠️ market.get check: {e}")
        
        return True
    
    return False


def check_token():
    """Читает токен из .env и проверяет."""
    env = read_env()
    token = env.get('VK_USER_TOKEN', '')
    
    if not token:
        print("❌ VK_USER_TOKEN не найден в .env")
        print("   Запусти: python3 vk_token_manager.py --auth")
        return
    
    print(f"🔍 Проверяю VK_USER_TOKEN ({token[:20]}...)")
    check_token_internal(token)


# ═══════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='VK Token Manager')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--auth', action='store_true', help='Генерировать URL для авторизации')
    group.add_argument('--exchange', type=str, metavar='CODE', help='Обменять code на token (запускать на VPS!)')
    group.add_argument('--save-token', type=str, metavar='TOKEN', help='Сохранить токен из Implicit Flow')
    group.add_argument('--check', action='store_true', help='Проверить текущий токен')
    
    args = parser.parse_args()
    
    if args.auth:
        generate_auth_url()
    elif args.exchange:
        exchange_code(args.exchange)
    elif args.save_token:
        save_token(args.save_token)
    elif args.check:
        check_token()
