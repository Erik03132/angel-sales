#!/usr/bin/env python3
"""
📢 OK Smart Autoposter — автоматическая публикация в Одноклассники.

Работает по той же схеме, что и vk_smart_poster.py:
  1. Сканирует .md файлы в папке группы
  2. Находит неопубликованные посты (сверка с ok_posted_log.json)
  3. Генерирует фото через Imagen 4.0 (Gemini API)
  4. Публикует 1 пост и обновляет лог

Нужные переменные в .env:
  OK_APP_ID         — ID приложения (из apiok.ru / vk.com/dev → OK)
  OK_APP_PUBLIC_KEY — Публичный ключ приложения
  OK_APP_SECRET_KEY — Секретный ключ приложения
  OK_ACCESS_TOKEN   — OAuth access_token пользователя (владелец группы)
  OK_PODVORYE_GROUP_ID — 70000050244449

Использование:
  python3 ok_smart_poster.py podvorye           # 1 пост «Своё Подворье»
  python3 ok_smart_poster.py podvorye --count 3 # 3 поста
  python3 ok_smart_poster.py podvorye --dry-run # без публикации
  python3 ok_smart_poster.py podvorye --list    # список неопубликованных

Получение токена:
  python3 ok_token_manager.py --auth
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_DIR = os.path.join(BASE_DIR, "agent")
sys.path.insert(0, AGENT_DIR)

from vk_smart_poster import _make_imagen_prompt, generate_imagen_photo, parse_all_posts

# ═══════════════════════════════════════════════
# Конфигурация
# ═══════════════════════════════════════════════

CONTENT_DIR = os.path.join(BASE_DIR, "vk_content")  # контент тот же, что и у ВК
OK_API_BASE = "https://api.ok.ru/fb.do"

GROUPS = {
    "podvorye": {
        "env_group_id": "OK_PODVORYE_GROUP_ID",
        "name": "Своё Подворье (OK)",
        "content_dir": os.path.join(CONTENT_DIR, "podvorye"),
        "posted_log": os.path.join(CONTENT_DIR, "podvorye", "ok_posted_log.json"),
        "default_photo_prompt": (
            "Charming Russian rural farmstead with wooden house, vegetable garden, "
            "free-range chickens on green grass, warm golden hour light. "
            "No text, no words, no letters, no watermarks."
        ),
    },
}


# ═══════════════════════════════════════════════
# OK API Client
# ═══════════════════════════════════════════════

class OKPoster:
    """Клиент OK REST API для публикации в группу."""

    API_BASE = "https://api.ok.ru/fb.do"

    def __init__(self, app_id: str, app_public_key: str, app_secret_key: str,
                 access_token: str, group_id: str):
        self.app_id = app_id
        self.app_public_key = app_public_key
        self.app_secret_key = app_secret_key
        self.access_token = access_token
        self.group_id = group_id  # числовой ID без знака минуса

    # ─── Подпись запроса ───────────────────────────────────────────

    def _sign(self, params: dict) -> str:
        """
        Формула подписи OK API:
          1. Параметры без access_token сортируем по алфавиту и склеиваем
          2. Добавляем MD5(access_token + app_secret_key)
          3. MD5 всей строки — это sig
        """
        token_md5 = hashlib.md5(
            (self.access_token + self.app_secret_key).encode("utf-8")
        ).hexdigest().lower()

        sorted_params = sorted(
            (k, v) for k, v in params.items() if k != "access_token"
        )
        param_str = "".join(f"{k}={v}" for k, v in sorted_params)
        sig_str = param_str + token_md5
        return hashlib.md5(sig_str.encode("utf-8")).hexdigest().lower()

    # ─── Базовый запрос ────────────────────────────────────────────

    def _call(self, method: str, extra_params: dict) -> dict:
        """Выполняет вызов OK API."""
        params = {
            "application_id": self.app_id,
            "application_key": self.app_public_key,
            "access_token": self.access_token,
            "method": method,
            "format": "json",
        }
        params.update(extra_params)
        params["sig"] = self._sign(params)

        data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(self.API_BASE, data=data)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ─── Проверка токена ───────────────────────────────────────────

    def check_token(self) -> dict:
        """Проверяет токен через users.getCurrentUser."""
        try:
            data = self._call("users.getCurrentUser", {"fields": "name,uid"})
            if "error_code" in data:
                return {"ok": False, "error": data.get("error_message", str(data))}
            return {"ok": True, "name": data.get("name", "?"), "uid": data.get("uid", "?")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ─── Загрузка фото ─────────────────────────────────────────────

    def upload_photo(self, photo_bytes: bytes) -> str | None:
        """
        Загружает фото в группу OK через 3-шаговый процесс:
          1. photos.getUploadUrl
          2. Multipart POST на upload_url
          3. photos.commit
        Возвращает photo_id или None.
        """
        # 1. Получить upload URL
        try:
            data = self._call("photos.getUploadUrl", {
                "count": "1",
                "gid": self.group_id,
            })
            if "error_code" in data:
                print(f"  ❌ photos.getUploadUrl: {data.get('error_message')}")
                return None
            upload_url = data.get("upload_url") or data.get("uploadUrl")
            if not upload_url:
                print(f"  ❌ photos.getUploadUrl: нет upload_url в ответе: {data}")
                return None
        except Exception as e:
            print(f"  ❌ photos.getUploadUrl exception: {e}")
            return None

        # 2. Multipart upload
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(photo_bytes)
                tmp_path = f.name

            boundary = "----FormBoundary" + hashlib.md5(photo_bytes[:32]).hexdigest()[:8]
            filename = "photo.png"
            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="photo"; filename="{filename}"\r\n'
                f"Content-Type: image/png\r\n\r\n"
            ).encode("utf-8") + photo_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

            req = urllib.request.Request(
                upload_url,
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                upload_result = json.loads(resp.read().decode("utf-8"))

        except Exception as e:
            print(f"  ❌ Photo upload exception: {e}")
            return None
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        # 3. Commit
        try:
            photo_ids_raw = upload_result.get("photos") or upload_result.get("photo_ids") or ""
            commit_data = self._call("photos.commit", {
                "photo_ids": str(photo_ids_raw),
                "gid": self.group_id,
            })
            if "error_code" in commit_data:
                print(f"  ❌ photos.commit: {commit_data.get('error_message')}")
                return None
            # OK возвращает список id фото
            photos = commit_data.get("photos") or []
            if photos:
                photo_id = photos[0].get("id") or photos[0].get("photo_id")
                print(f"  📸 Фото загружено в OK: {photo_id}")
                return str(photo_id)
        except Exception as e:
            print(f"  ❌ photos.commit exception: {e}")
        return None

    # ─── Публикация поста ──────────────────────────────────────────

    def post(self, text: str, photo_id: str | None = None) -> str | None:
        """
        Публикует пост на стене группы через mediatopic.add.
        Возвращает topic_id или None.
        """
        # Формируем attachment JSON для OK
        attachment: dict = {"media": []}

        if photo_id:
            attachment["media"].append({
                "type": "photo",
                "list": [{"id": photo_id}],
            })

        attachment["media"].append({
            "type": "text",
            "text": text,
        })

        try:
            data = self._call("mediatopic.add", {
                "gid": self.group_id,
                "type": "GROUP_THEME",
                "attachment": json.dumps(attachment, ensure_ascii=False),
            })
            if "error_code" in data:
                print(f"  ❌ mediatopic.add: [{data.get('error_code')}] {data.get('error_message')}")
                return None
            topic_id = str(data) if isinstance(data, (str, int)) else data.get("id", "?")
            return topic_id
        except Exception as e:
            print(f"  ❌ mediatopic.add exception: {e}")
            return None


# ═══════════════════════════════════════════════
# Вспомогательные функции
# ═══════════════════════════════════════════════

def load_env() -> dict:
    """Читает .env из корня проекта."""
    env = {}
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    # Дополняем из os.environ (приоритет env)
    for k, v in os.environ.items():
        if k not in env:
            env[k] = v
    return env


def load_posted(path: str) -> dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_posted(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_next_posts(content_dir: str, posted_log_path: str, count: int = 1) -> list:
    """Возвращает список из count неопубликованных постов."""
    all_posts = parse_all_posts(content_dir)
    posted = load_posted(posted_log_path)
    posted_keys = set(posted.get("_keys", []))
    posted_indices = set(str(k) for k in posted.keys() if k != "_keys")

    unpublished = []
    for post in all_posts:
        key = post.get("post_id_key", "")
        idx = str(post.get("index", 0))
        if key not in posted_keys and idx not in posted_indices:
            unpublished.append(post)

    return unpublished[:count]


# ═══════════════════════════════════════════════
# TG уведомление
# ═══════════════════════════════════════════════

def send_tg_report(results_all: dict, env: dict) -> None:
    tg_token = env.get("ANGELOCHKA_BOT_TOKEN", "")
    chat_id = env.get("OWNER_CHAT_ID", "176203333")
    if not tg_token:
        return

    total = sum(len(r) for r in results_all.values())
    ok_count = sum(1 for rs in results_all.values() for r in rs if r.get("status") == "ok")

    lines = [f"📢 *OK Autoposter* — {datetime.now().strftime('%d.%m.%Y %H:%M')}", ""]
    for group, results in results_all.items():
        name = GROUPS[group]["name"]
        for r in results:
            if r.get("status") == "ok":
                url = r.get("url", "")
                lines.append(f"✅ {name}: [пост]({url})" if url else f"✅ {name}: опубликован")
            elif r.get("status") == "dry-run":
                lines.append(f"🔸 {name}: dry-run")
            else:
                lines.append(f"❌ {name}: ошибка")

    lines.append(f"\nИтого: {ok_count}/{total}")
    text = "\n".join(lines)

    try:
        proxy = env.get("TELEGRAM_PROXY", "")
        cmd = ["curl", "-s", "--max-time", "10"]
        if proxy:
            cmd.extend(["--proxy", proxy])
        cmd.extend([
            "-X", "POST",
            f"https://api.telegram.org/bot{tg_token}/sendMessage",
            "-d", f"chat_id={chat_id}&text={urllib.parse.quote(text)}&parse_mode=Markdown&disable_web_page_preview=true",
        ])
        subprocess.run(cmd, timeout=15, capture_output=True)
    except Exception as e:
        print(f"  ⚠️ TG report: {e}")


# ═══════════════════════════════════════════════
# Логика публикации
# ═══════════════════════════════════════════════

def publish_group(group_key: str, env: dict, count: int = 1, dry_run: bool = False) -> list:
    """Публикует count постов для указанной группы."""
    cfg = GROUPS[group_key]
    group_id = env.get(cfg["env_group_id"], "").lstrip("-")

    app_id = env.get("OK_APP_ID", "")
    app_public_key = env.get("OK_APP_PUBLIC_KEY", "")
    app_secret_key = env.get("OK_APP_SECRET_KEY", "")
    access_token = env.get("OK_ACCESS_TOKEN", "")

    if not group_id:
        print(f"❌ {cfg['name']}: {cfg['env_group_id']} не найден в .env")
        return []

    if not dry_run:
        missing = []
        for var in ("OK_APP_ID", "OK_APP_PUBLIC_KEY", "OK_APP_SECRET_KEY", "OK_ACCESS_TOKEN"):
            if not env.get(var):
                missing.append(var)
        if missing:
            print(f"❌ {cfg['name']}: Не заданы переменные: {', '.join(missing)}")
            print("   Добавьте их в .env и повторите попытку.")
            print("   Для получения токена: python3 ok_token_manager.py --auth")
            return []

    posts = get_next_posts(cfg["content_dir"], cfg["posted_log"], count)
    if not posts:
        print(f"✅ {cfg['name']}: все посты опубликованы!")
        return []

    print(f"\n{'═' * 50}")
    print(f"  📢 {cfg['name']} — {len(posts)} пост(ов) к публикации")
    print(f"{'═' * 50}")

    if not dry_run:
        poster = OKPoster(app_id, app_public_key, app_secret_key, access_token, group_id)
        info = poster.check_token()
        if info.get("ok"):
            print(f"  ✅ Токен OK: {info['name']} (uid {info['uid']})")
        else:
            print(f"  ⚠️ Токен: {info.get('error', '?')}")
    else:
        poster = None

    results = []
    posted_log = load_posted(cfg["posted_log"])
    posted_keys = set(posted_log.get("_keys", []))

    for i, post in enumerate(posts):
        print(f"\n  [{i + 1}/{len(posts)}] {post['text'][:60]}...")

        if dry_run:
            print("  🔸 DRY-RUN: пропуск публикации")
            results.append({"status": "dry-run", "text": post["text"][:50]})
            continue

        # Фото через Imagen 4.0
        photo_id = None
        prompt = _make_imagen_prompt(post["text"], post.get("meta", {}), cfg["default_photo_prompt"])
        print(f"  🎨 Imagen 4.0: «{prompt[:60]}»...")
        photo_bytes = generate_imagen_photo(prompt, env)
        if photo_bytes:
            photo_id = poster.upload_photo(photo_bytes)

        # Публикация
        print("  📝 Публикую в OK...")
        topic_id = poster.post(post["text"], photo_id=photo_id)

        if topic_id:
            url = f"https://ok.ru/group/{group_id}/topic/{topic_id}"
            print(f"  ✅ Опубликован: {url}")

            key = post.get("post_id_key", str(post.get("index", i)))
            posted_keys.add(key)
            posted_log[str(post.get("index", i + 1))] = {
                "topic_id": topic_id,
                "url": url,
                "posted_at": datetime.now().isoformat(),
                "source_file": post.get("source_file", "?"),
                "text_preview": post["text"][:80],
                "has_photo": bool(photo_id),
            }
            posted_log["_keys"] = list(posted_keys)
            save_posted(cfg["posted_log"], posted_log)

            results.append({"status": "ok", "topic_id": topic_id, "url": url})
        else:
            print("  ❌ Не опубликован")
            results.append({"status": "fail"})

        if i < len(posts) - 1:
            print("  ⏳ Пауза 3 сек...")
            time.sleep(3)

    return results


# ═══════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="OK Smart Autoposter")
    parser.add_argument("group", choices=list(GROUPS.keys()), help="Группа для постинга")
    parser.add_argument("--count", "-n", type=int, default=1, help="Количество постов (по умолчанию 1)")
    parser.add_argument("--dry-run", action="store_true", help="Без публикации (только просмотр)")
    parser.add_argument("--list", action="store_true", help="Показать неопубликованные посты")
    args = parser.parse_args()

    env = load_env()
    groups = list(GROUPS.keys()) if args.group == "all" else [args.group]

    if args.list:
        for g in groups:
            cfg = GROUPS[g]
            posts = get_next_posts(cfg["content_dir"], cfg["posted_log"], count=100)
            print(f"\n{'═' * 50}")
            print(f"  {cfg['name']}: {len(posts)} неопубликованных")
            print(f"{'═' * 50}")
            for idx, p in enumerate(posts[:10], 1):
                print(f"  {idx}. [{p.get('source_file', '?')}] {p['text'][:70]}...")
        return

    results_all = {}
    for g in groups:
        results = publish_group(g, env, count=args.count, dry_run=args.dry_run)
        results_all[g] = results

    if not args.dry_run:
        send_tg_report(results_all, env)

    total = sum(len(r) for r in results_all.values())
    ok_count = sum(1 for rs in results_all.values() for r in rs if r.get("status") == "ok")
    print(f"\n{'═' * 50}")
    print(f"  📊 ИТОГО: {ok_count}/{total} опубликовано")
    print(f"{'═' * 50}")


if __name__ == "__main__":
    main()
