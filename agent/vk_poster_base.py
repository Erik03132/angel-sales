#!/usr/bin/env python3
"""
📦 VK POSTER BASE — Общий модуль для всех VK-постеров.
Использует библиотеку vk_api (pip install vk_api) вместо самописных urllib-обёрток.

Предоставляет:
- VKPoster — класс для постинга с фото, опросами, отложенным постингом
- load_env() — загрузка .env
- parse_posts_from_file() — парсинг markdown-файлов с постами
"""

import json
import os
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request

try:
    import vk_api
    from vk_api import VkUpload
    VK_API_LIB = True
except ImportError:
    VK_API_LIB = False
    print("⚠️ vk_api не установлен. Выполни: pip install vk_api")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ═══════════════════════════════════════════════
# .env загрузка
# ═══════════════════════════════════════════════

def load_env(path=None):
    """Загрузка .env вручную (без dotenv, для совместимости с VPS)."""
    if path is None:
        path = os.path.join(BASE_DIR, ".env")
    env = {}
    if os.path.exists(path):
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip()
    return env


# ═══════════════════════════════════════════════
# Каскадный поиск фото (Unsplash → Pexels → Pixabay) через curl + прокси
# ═══════════════════════════════════════════════

def _curl_get(url, proxy, auth_header=None):
    """curl GET с поддержкой SOCKS5 прокси. Возвращает response body или None."""
    cmd = ["curl", "-s", "--max-time", "15", "--connect-timeout", "10"]
    if proxy:
        cmd.extend(["--proxy", proxy])
    if auth_header:
        cmd.extend(["-H", auth_header])
    cmd.append(url)
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=20)
        if result.returncode == 0 and result.stdout:
            return result.stdout.decode("utf-8")
    except Exception as e:
        print(f"⚠️ curl error: {e}")
    return None


def _fetch_unsplash(keywords, api_key, proxy):
    query = urllib.parse.quote(keywords)
    url = f"https://api.unsplash.com/search/photos?query={query}&per_page=1&orientation=landscape"
    resp = _curl_get(url, proxy, f"Authorization: Client-ID {api_key}")
    if not resp:
        return None
    try:
        data = json.loads(resp)
        results = data.get("results", [])
        if results:
            return results[0]["urls"]["regular"]
    except Exception as e:
        print(f"⚠️ Unsplash parse: {e}")
    return None


def _fetch_pexels(keywords, api_key, proxy):
    query = urllib.parse.quote(keywords)
    url = f"https://api.pexels.com/v1/search?query={query}&per_page=1"
    resp = _curl_get(url, proxy, f"Authorization: {api_key}")
    if not resp:
        return None
    try:
        data = json.loads(resp)
        photos = data.get("photos", [])
        if photos:
            return photos[0]["src"]["large"]
    except Exception as e:
        print(f"⚠️ Pexels parse: {e}")
    return None


def _fetch_pixabay(keywords, api_key, proxy):
    query = urllib.parse.quote(keywords)
    url = f"https://pixabay.com/api/?key={api_key}&q={query}&image_type=photo&per_page=3&lang=ru"
    resp = _curl_get(url, proxy)
    if not resp:
        return None
    try:
        data = json.loads(resp)
        hits = data.get("hits", [])
        if hits:
            return hits[0]["webformatURL"]
    except Exception as e:
        print(f"⚠️ Pixabay parse: {e}")
    return None


def _download_photo(url, proxy):
    """Скачивает фото через curl+прокси во временный файл."""
    suffix = ".png" if "png" in url.lower() else ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = tmp.name
    tmp.close()

    cmd = ["curl", "-sL", "--max-time", "20", "--connect-timeout", "10"]
    if proxy:
        cmd.extend(["--proxy", proxy])
    cmd.extend(["-o", tmp_path, url])

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=25)
        if result.returncode == 0 and os.path.getsize(tmp_path) > 1024:
            return tmp_path
        print(f"⚠️ Скачать фото не удалось: curl={result.returncode}, size={os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0}")
    except Exception as e:
        print(f"⚠️ Скачать фото не удалось: {e}")

    if os.path.exists(tmp_path):
        os.unlink(tmp_path)
    return None


def fetch_photo_cascade(keywords, env):
    """Каскадный поиск фото. Возвращает путь к tmp-файлу или None."""
    proxy = env.get("TELEGRAM_PROXY", "")
    for fetcher, key_name, name in [
        (_fetch_unsplash, "UNSPLASH_ACCESS_KEY", "Unsplash"),
        (_fetch_pexels, "PEXELS_API_KEY", "Pexels"),
        (_fetch_pixabay, "PIXABAY_API_KEY", "Pixabay"),
    ]:
        api_key = env.get(key_name, "")
        if not api_key:
            continue
        photo_url = fetcher(keywords, api_key, proxy)
        if photo_url:
            print(f"📷 {name}: нашли фото → {photo_url[:60]}...")
            path = _download_photo(photo_url, proxy)
            if path:
                return path
    return None


# ═══════════════════════════════════════════════
# VKPoster — основной класс
# ═══════════════════════════════════════════════

class VKPoster:
    """
    Универсальный постер для VK-сообществ.
    Использует vk_api для всех операций.
    """

    def __init__(self, token, group_id, env=None):
        if not VK_API_LIB:
            raise ImportError("vk_api не установлен: pip install vk_api")

        self.group_id = str(group_id).lstrip("-")
        self.env = env or load_env()

        # Инициализация vk_api (group token — для постинга)
        self.vk_session = vk_api.VkApi(token=token)
        self.vk = self.vk_session.get_api()

        # User token для загрузки фото (VK API требует user auth)
        user_token = self.env.get("VK_USER_TOKEN", "")
        if user_token:
            self.user_session = vk_api.VkApi(token=user_token)
            self.upload = VkUpload(self.user_session)
        else:
            self.user_session = None
            self.upload = VkUpload(self.vk_session)  # fallback

    def check_token(self):
        """Проверка токена — возвращает информацию о группе."""
        try:
            result = self.vk.groups.getById(
                group_id=self.group_id,
                fields="members_count,description,status"
            )
            group = result["groups"][0] if "groups" in result else result[0]
            return {
                "ok": True,
                "name": group.get("name", "?"),
                "members": group.get("members_count", 0),
                "description": group.get("description", ""),
            }
        except vk_api.exceptions.ApiError as e:
            return {"ok": False, "error": str(e)}

    def upload_photo(self, photo_path):
        """
        Загрузка фото на стену группы (3 попытки).
        Возвращает attachment-строку 'photo-GID_PID' или None.
        """
        if not photo_path or not os.path.exists(photo_path):
            return None
        for attempt in range(1, 4):
            try:
                photos = self.upload.photo_wall(
                    photo_path,
                    group_id=int(self.group_id)
                )
                if photos:
                    p = photos[0]
                    attachment = f"photo{p['owner_id']}_{p['id']}"
                    print(f"📸 Фото загружено: {attachment}")
                    return attachment
                print(f"⚠️ Пустой ответ, попытка {attempt}")
            except Exception as e:
                print(f"⚠️ Ошибка загрузки фото (попытка {attempt}): {e}")
            if attempt < 3:
                import time
                time.sleep(3)
        return None

    def upload_photo_from_url(self, keywords, group_name=""):
        """Сначала проверяет photo_cache.json, затем каскадный поиск + загрузка."""
        # ── Шаг 0: Проверяем кэш (фото уже загружены в VK через photo_cache_builder) ──
        cache_file = os.path.join(BASE_DIR, "data", "photo_cache.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                kw_lower = keywords.lower().strip()
                # Точное совпадение с группой
                for prefix in [group_name, ""]:
                    cache_key = f"{prefix}::{kw_lower}" if prefix else kw_lower
                    if cache_key in cache and cache[cache_key]:
                        print(f"💾 Кэш: {cache[cache_key]}")
                        return cache[cache_key]
                # Частичное совпадение
                for k, v in cache.items():
                    if kw_lower in k.lower() and v:
                        print(f"💾 Кэш (частичное): «{keywords}» → {v}")
                        return v
            except Exception as e:
                print(f"⚠️ Кэш недоступен: {e}")

        # ── Шаг 1: Каскад стоков ──
        photo_path = fetch_photo_cascade(keywords, self.env)
        if not photo_path:
            return None
        try:
            return self.upload_photo(photo_path)
        finally:
            if photo_path and os.path.exists(photo_path):
                os.unlink(photo_path)

    def post(self, message, attachments=None, publish_date=None):
        """
        Публикация поста на стене группы.
        attachments — строка вида 'photo-123_456' или None.
        publish_date — datetime для отложенного поста или None.
        """
        params = {
            "owner_id": f"-{self.group_id}",
            "from_group": 1,
            "message": message,
        }
        if attachments:
            params["attachments"] = attachments
        if publish_date:
            params["publish_date"] = int(publish_date.timestamp())

        try:
            result = self.vk.wall.post(**params)
            post_id = result["post_id"]
            return post_id
        except vk_api.exceptions.ApiError as e:
            print(f"❌ VK API: {e}")
            return None

    def create_poll(self, question, answers, is_multiple=True, is_anonymous=False):
        """Создание опроса. Возвращает attachment-строку или None."""
        try:
            result = self.vk.polls.create(
                question=question,
                is_anonymous=1 if is_anonymous else 0,
                is_multiple=1 if is_multiple else 0,
                owner_id=f"-{self.group_id}",
                add_answers=json.dumps(answers, ensure_ascii=False),
            )
            return f"poll{result['owner_id']}_{result['id']}"
        except vk_api.exceptions.ApiError as e:
            print(f"❌ Ошибка создания опроса: {e}")
            return None

    def get_wall_count(self):
        """Количество постов на стене."""
        try:
            result = self.vk.wall.get(owner_id=f"-{self.group_id}", count=0)
            return result["count"]
        except Exception:
            return -1

    def delete_post(self, post_id):
        """Удаление поста со стены."""
        try:
            self.vk.wall.delete(owner_id=f"-{self.group_id}", post_id=post_id)
            return True
        except vk_api.exceptions.ApiError as e:
            print(f"❌ Ошибка удаления поста {post_id}: {e}")
            return False


# ═══════════════════════════════════════════════
# Парсер постов из markdown
# ═══════════════════════════════════════════════

def parse_posts_from_file(filepath):
    """Парсинг постов из markdown-файла (формат week1_posts.md / starter_posts.md)."""
    if not os.path.exists(filepath):
        print(f"❌ Файл не найден: {filepath}")
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    raw_posts = re.split(r'\n---\n', content)
    posts = []

    for i, raw in enumerate(raw_posts):
        raw = raw.strip()
        if not raw:
            continue

        lines = raw.split("\n")
        meta = {}
        text_lines = []

        for line in lines:
            if line.startswith("# ПОСТ"):
                meta["title"] = line.lstrip("# ").strip()
            elif line.startswith("# Рубрика:"):
                meta["rubric"] = line.replace("# Рубрика:", "").strip()
            elif line.startswith("# Хэштеги:"):
                meta["hashtags"] = line.replace("# Хэштеги:", "").strip()
            elif line.startswith("# Тип:"):
                meta["type"] = line.replace("# Тип:", "").strip()
            elif line.startswith("# ВЧ-ключи:"):
                meta["keywords"] = line.replace("# ВЧ-ключи:", "").strip()
            elif line.startswith("# ФОТО-ЗАПРОС:"):
                meta["photo_query"] = line.replace("# ФОТО-ЗАПРОС:", "").strip()
            elif line.startswith("# ВАЖНО:") or line.startswith("# ПОМЕТКА:") or line.startswith("# ПРИМЕЧАНИЕ:"):
                meta["note"] = line.split(":", 1)[1].strip()
            elif line.startswith("> ") or line.startswith("# 📝"):
                continue
            else:
                text_lines.append(line)

        post_text = "\n".join(text_lines).strip()
        if not post_text and not meta:
            continue

        is_poll = "ОПРОС" in meta.get("type", "") or "[ОПРОС" in post_text

        post = {
            "index": i + 1,
            "meta": meta,
            "text": post_text,
            "is_poll": is_poll,
        }

        # Для опроса — извлекаем варианты
        if is_poll:
            poll_text, poll_options = _extract_poll_data(post_text)
            post["poll_text"] = poll_text
            post["poll_options"] = poll_options

        posts.append(post)

    return posts


def _extract_poll_data(text):
    """Извлекает текст поста и варианты опроса."""
    lines = text.split("\n")
    poll_options = []
    clean_lines = []
    in_poll_section = False
    emoji_starters = ["🐔", "🐣", "🦆", "🦃", "🐇", "🐐", "🐝", "🌱", "🏙"]

    for line in lines:
        if "[ОПРОС" in line:
            in_poll_section = True
            continue
        if in_poll_section and line.startswith("Вопрос:"):
            continue
        if in_poll_section and line.startswith("Варианты:"):
            continue
        if in_poll_section and any(line.strip().startswith(e) for e in emoji_starters):
            poll_options.append(line.strip())
            continue
        if line.strip().startswith("Текст поста:"):
            continue
        if not in_poll_section:
            clean_lines.append(line)

    return "\n".join(clean_lines).strip(), poll_options


# ═══════════════════════════════════════════════
# Утилиты для лога
# ═══════════════════════════════════════════════

def load_posted_log(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_posted_log(path, log):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
