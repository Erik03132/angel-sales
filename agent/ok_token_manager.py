#!/usr/bin/env python3
"""
🔑 OK Token Manager — получение и проверка токена OK API.

Два шага:
  1. --auth     → Генерирует OAuth URL (открыть в браузере)
  2. --save TOKEN → Сохраняет токен в .env
  3. --check    → Проверяет текущий токен

После авторизации вы увидите redirect на ok_callback с параметром access_token в URL.

Использование:
  python3 ok_token_manager.py --auth
  python3 ok_token_manager.py --save "ВСТАВЬТЕ_ТОКЕН_СЮДА"
  python3 ok_token_manager.py --check
"""

import argparse
import hashlib
import json
import os
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env")

OK_OAUTH_URL = "https://connect.ok.ru/oauth/authorize"
OK_API_BASE = "https://api.ok.ru/fb.do"

# Права доступа: публикация в группах и загрузка фото
SCOPE = "PHOTO_CONTENT;PHOTO_UPLOAD;GROUP_CONTENT;VALUABLE_CONTENT"
REDIRECT_URI = "https://localhost/ok_callback"


# ═══════════════════════════════════════════════
# .env утилиты
# ═══════════════════════════════════════════════

def read_env() -> dict:
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    return env


def update_env_var(key: str, value: str) -> None:
    lines = []
    found = False
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"{key}={value}\n")

    with open(ENV_PATH, "w") as f:
        f.writelines(new_lines)

    os.environ[key] = value
    print(f"  ✅ {key} сохранён в {ENV_PATH}")


# ═══════════════════════════════════════════════
# Шаг 1: OAuth URL
# ═══════════════════════════════════════════════

def generate_auth_url() -> None:
    env = read_env()
    app_id = env.get("OK_APP_ID", "")

    if not app_id:
        print("❌ OK_APP_ID не найден в .env!")
        print()
        print("   Сначала создайте приложение на apiok.ru:")
        print("   1. Откройте https://apiok.ru → API → Разработка → Приложение")
        print("   2. Создайте приложение (через VK Mini Apps для OK)")
        print("   3. Скопируйте App ID и ключи в .env:")
        print()
        print("   OK_APP_ID=<ваш_app_id>")
        print("   OK_APP_PUBLIC_KEY=<ваш_public_key>")
        print("   OK_APP_SECRET_KEY=<ваш_secret_key>")
        print("   OK_PODVORYE_GROUP_ID=70000050244449")
        print()
        return

    # Implicit Flow — токен сразу в URL после авторизации
    params = {
        "client_id": app_id,
        "scope": SCOPE,
        "response_type": "token",
        "redirect_uri": REDIRECT_URI,
        "layout": "w",
    }
    auth_url = OK_OAUTH_URL + "?" + urllib.parse.urlencode(params)

    print("=" * 65)
    print("🔑 OK Token Manager — Авторизация")
    print("=" * 65)
    print()
    print("📌 Шаг 1: Откройте эту ссылку в браузере (войдя как владелец группы):")
    print()
    print(f"  👉 {auth_url}")
    print()
    print("📌 Шаг 2: Подтвердите права доступа")
    print()
    print("📌 Шаг 3: После редиректа скопируйте access_token из URL:")
    print("  URL будет вида:")
    print("  https://localhost/ok_callback#access_token=XXXXXXXX&...")
    print()
    print("📌 Шаг 4: Сохраните токен:")
    print("  python3 ok_token_manager.py --save ВСТАВЬТЕ_ТОКЕН")
    print()
    print("=" * 65)


# ═══════════════════════════════════════════════
# Шаг 2: Сохранение токена
# ═══════════════════════════════════════════════

def save_token(token: str) -> None:
    update_env_var("OK_ACCESS_TOKEN", token)
    print()
    check_token_internal(token)


# ═══════════════════════════════════════════════
# Проверка токена
# ═══════════════════════════════════════════════

def _make_sig(params: dict, access_token: str, app_secret_key: str) -> str:
    token_md5 = hashlib.md5(
        (access_token + app_secret_key).encode("utf-8")
    ).hexdigest().lower()
    sorted_params = sorted((k, v) for k, v in params.items() if k != "access_token")
    param_str = "".join(f"{k}={v}" for k, v in sorted_params)
    sig_str = param_str + token_md5
    return hashlib.md5(sig_str.encode("utf-8")).hexdigest().lower()


def check_token_internal(token: str) -> None:
    env = read_env()
    app_id = env.get("OK_APP_ID", "")
    app_public_key = env.get("OK_APP_PUBLIC_KEY", "")
    app_secret_key = env.get("OK_APP_SECRET_KEY", "")

    if not all([app_id, app_public_key, app_secret_key]):
        print("⚠️  OK_APP_ID / OK_APP_PUBLIC_KEY / OK_APP_SECRET_KEY не заданы в .env")
        print("   Проверить токен не получится без ключей приложения.")
        return

    params = {
        "application_id": app_id,
        "application_key": app_public_key,
        "access_token": token,
        "method": "users.getCurrentUser",
        "fields": "name,uid",
        "format": "json",
    }
    params["sig"] = _make_sig(params, token, app_secret_key)

    try:
        data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(OK_API_BASE, data=data)
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        if "error_code" in result:
            print(f"❌ Токен невалиден: [{result['error_code']}] {result.get('error_message')}")
        else:
            print(f"✅ Токен валиден: {result.get('name', '?')} (uid: {result.get('uid', '?')})")
            print(f"   Группа: OK_PODVORYE_GROUP_ID = {env.get('OK_PODVORYE_GROUP_ID', '❌ не задан')}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")


def check_token() -> None:
    env = read_env()
    token = env.get("OK_ACCESS_TOKEN", "")
    if not token:
        print("❌ OK_ACCESS_TOKEN не найден в .env")
        print("   Запустите: python3 ok_token_manager.py --auth")
        return
    print(f"🔍 Проверяю OK_ACCESS_TOKEN ({token[:20]}...)")
    check_token_internal(token)


# ═══════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OK Token Manager")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--auth", action="store_true", help="Генерировать OAuth URL")
    group.add_argument("--save", type=str, metavar="TOKEN", help="Сохранить токен в .env")
    group.add_argument("--check", action="store_true", help="Проверить текущий токен")

    args = parser.parse_args()

    if args.auth:
        generate_auth_url()
    elif args.save:
        save_token(args.save)
    elif args.check:
        check_token()
