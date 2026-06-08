#!/usr/bin/env python3
"""
📸 PHOTO CASCADE — Каскадный загрузчик фото для VK постов
Порядок: Unsplash (1) → Pexels (2) → Pixabay (3) → без фото (fallback)

Использование:
    from photo_cascade import get_photo_attachment
    attachment = get_photo_attachment(
        keywords="цыплята бройлер",
        vk_token=VK_TOKEN,
        vk_group_id=VK_GROUP_ID
    )
    # attachment = "photo-238316002_123456" или "" если ничего не нашли

Диагностика:
    python photo_cascade.py test
    python photo_cascade.py test --keywords="цыплята"
"""

import json
import os
import subprocess
import sys
import tempfile

# ─── Leonardo.ai генератор ──────────────────
import requests as _requests


def generate_leonardo(keywords: str, api_key: str) -> str | None:
    """Генерирует фото через Leonardo.ai Vision XL. Возвращает путь к файлу или None."""
    base_url = "https://cloud.leonardo.ai/api/rest/v1"
    model_id = "5c232a9e-9061-4777-980a-ddc8e65647c6"
    neg_prompt = (
        "text, watermark, logo, signature, stamp, "
        "deformed, mutated, extra limbs, extra legs, extra heads, extra fingers, "
        "ugly, bad anatomy, disfigured, malformed, "
        "blurry, low quality, pixelated, "
        "cartoon, illustration, drawing, painting, digital art, "
        "surreal, abstract, CGI, 3D render, anime, "
        "oversaturated, neon colors, "
        "cowboy hat, cowboy boots, american flag, US style, Texas, "
        "american farmer, american barn, american landscape"
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    prompt = (
        f"Professional editorial photograph for farming magazine. "
        f"{keywords}. "
        f"Realistic Russian homestead, Russian countryside, Slavic rural setting. "
        f"Natural daylight, warm tones. "
        f"No american style, no cowboy hats, no US farm aesthetic. "
        f"Shot on Canon EOS R5, 35mm lens, f/5.6. "
        f"Editorial magazine quality, realistic, high detail."
    )
    payload = {
        "prompt": prompt,
        "negative_prompt": neg_prompt,
        "modelId": model_id,
        "width": 1024,
        "height": 1024,
        "num_images": 1,
        "alchemy": True,
    }

    try:
        resp = _requests.post(
            f"{base_url}/generations", headers=headers, json=payload, timeout=60
        )
        data = resp.json()
        if "sdGenerationJob" not in data:
            print(f"  ❌ Leonardo API error: {data.get('message', str(data)[:200])}")
            return None

        gen_id = data["sdGenerationJob"]["generationId"]
        for i in range(30):
            import time as _time
            _time.sleep(4)
            status = _requests.get(
                f"{base_url}/generations/{gen_id}", headers=headers, timeout=30
            ).json()
            job = status.get("generations_by_pk", {})
            s = job.get("status", "UNKNOWN")
            if s == "COMPLETE":
                imgs = job.get("generated_images", [])
                if imgs:
                    import tempfile
                    img_data = _requests.get(imgs[0]["url"], timeout=60).content
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                    tmp.write(img_data)
                    tmp.close()
                    print(f"  ✅ Leonardo: {os.path.getsize(tmp.name)//1024}KB")
                    return tmp.name
                return None
            elif s == "FAILED":
                print("  ❌ Leonardo: generation FAILED")
                return None
        print("  ❌ Leonardo: timeout")
        return None
    except Exception as e:
        print(f"  ❌ Leonardo: {str(e)[:100]}")
        return None


# ─── VK API с retry ───────────────────────────────────────────────────────

def _vk_api_call(method: str, params: dict, token: str, timeout: int = 15) -> dict:
    """Вызов VK API через curl с retry (3 попытки на транспорт)."""
    params["access_token"] = token
    params["v"] = "5.199"
    url = f"https://api.vk.com/method/{method}"
    raw = _curl_post(url, data=params, timeout=timeout, retries=3)
    return json.loads(raw)

# ─── curl-транспорт с retry (устойчив к нестабильности VPN) ──────────────────
import time
import urllib.parse


def _curl_get(url: str, headers: dict = None, timeout: int = 12, retries: int = 3) -> bytes:
    """
    HTTP GET через curl с retry. Без --interface: использует системный маршрут (VPN или прямой).
    Retry справляется с нестабильностью VPN-туннеля.
    """
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            cmd = [
                "curl", "-s", "-L",
                "--max-time", str(timeout),
                "--connect-timeout", "6",
                "--retry", "0",   # retry управляем сами
                url,
            ]
            if headers:
                for k, v in headers.items():
                    cmd += ["-H", f"{k}: {v}"]
            result = subprocess.run(cmd, capture_output=True, timeout=timeout + 8)
            if result.returncode == 0 and result.stdout:
                return result.stdout
            err = result.stderr.decode("utf-8", errors="replace").strip()
            last_err = f"curl code {result.returncode}: {err}"
        except Exception as e:
            last_err = str(e)
        if attempt < retries:
            time.sleep(2)
    raise OSError(f"curl GET failed after {retries} attempts: {last_err}")


def _curl_post(url: str, data: dict = None, timeout: int = 15, retries: int = 3) -> bytes:
    """HTTP POST через curl с retry."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            cmd = [
                "curl", "-s",
                "--max-time", str(timeout),
                "--connect-timeout", "6",
                url,
            ]
            if data:
                for k, v in data.items():
                    cmd += ["-d", f"{k}={urllib.parse.quote(str(v))}"]
            result = subprocess.run(cmd, capture_output=True, timeout=timeout + 8)
            if result.returncode == 0 and result.stdout:
                return result.stdout
            last_err = result.stderr.decode("utf-8", errors="replace").strip()
        except Exception as e:
            last_err = str(e)
        if attempt < retries:
            time.sleep(2)
    raise OSError(f"curl POST failed after {retries} attempts: {last_err}")


def _curl_upload(url: str, field: str, filepath: str, timeout: int = 30, retries: int = 3) -> bytes:
    """Multipart upload через curl с retry."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            cmd = [
                "curl", "-s",
                "--max-time", str(timeout),
                "--connect-timeout", "6",
                "-F", f"{field}=@{filepath}",
                url,
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=timeout + 8)
            if result.returncode == 0 and result.stdout:
                return result.stdout
            last_err = result.stderr.decode("utf-8", errors="replace").strip()
        except Exception as e:
            last_err = str(e)
        if attempt < retries:
            time.sleep(2)
    raise OSError(f"curl upload failed after {retries} attempts: {last_err}")


# ─── Загрузка .env ────────────────────────────────────────────────────────────

def load_env(path=None):
    if path is None:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    env = {}
    if os.path.exists(path):
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip()
    return env


# ─── Источники фото ───────────────────────────────────────────────────────────

def fetch_unsplash(keywords: str, api_key: str) -> str | None:
    """Возвращает прямую ссылку на фото с Unsplash или None."""
    if not api_key:
        return None
    try:
        query = urllib.parse.quote(keywords)
        url = f"https://api.unsplash.com/search/photos?query={query}&per_page=1&orientation=landscape"
        raw = _curl_get(url, headers={"Authorization": f"Client-ID {api_key}"}, timeout=10)
        data = json.loads(raw)
        results = data.get("results", [])
        if results:
            photo_url = results[0]["urls"]["regular"]
            print(f"📷 Unsplash: нашли фото → {photo_url[:60]}...")
            return photo_url
    except Exception as e:
        print(f"⚠️ Unsplash ошибка: {e}")
    return None


def fetch_pexels(keywords: str, api_key: str) -> str | None:
    """Возвращает прямую ссылку на фото с Pexels или None."""
    if not api_key:
        return None
    try:
        query = urllib.parse.quote(keywords)
        url = f"https://api.pexels.com/v1/search?query={query}&per_page=1"
        raw = _curl_get(url, headers={"Authorization": api_key}, timeout=10)
        data = json.loads(raw)
        photos = data.get("photos", [])
        if photos:
            photo_url = photos[0]["src"]["large"]
            print(f"📷 Pexels: нашли фото → {photo_url[:60]}...")
            return photo_url
    except Exception as e:
        print(f"⚠️ Pexels ошибка: {e}")
    return None


def fetch_pixabay(keywords: str, api_key: str) -> str | None:
    """Возвращает прямую ссылку на фото с Pixabay или None."""
    if not api_key:
        return None
    try:
        query = urllib.parse.quote(keywords)
        url = f"https://pixabay.com/api/?key={api_key}&q={query}&image_type=photo&per_page=3&lang=ru"
        raw = _curl_get(url, timeout=10)
        data = json.loads(raw)
        hits = data.get("hits", [])
        if hits:
            photo_url = hits[0]["webformatURL"]
            print(f"📷 Pixabay: нашли фото → {photo_url[:60]}...")
            return photo_url
    except Exception as e:
        print(f"⚠️ Pixabay ошибка: {e}")
    return None


# ─── AI-генерация (fallback когда стоки не нашли фото) ────────────────────────

def generate_fal_flux(keywords: str, api_key: str) -> str | None:
    """
    Генерация фото через FAL.ai Flux Schnell (~$0.003, ~2 сек).
    Возвращает URL сгенерированного изображения.
    """
    if not api_key:
        return None
    try:
        prompt = f"Professional realistic photograph: {keywords}. Natural lighting, high quality, no text or watermarks."
        body = json.dumps({
            "prompt": prompt,
            "image_size": "landscape_16_9",
            "num_images": 1,
            "enable_safety_checker": False,
        })
        cmd = [
            "curl", "-s",
            "--max-time", "30",
            "--connect-timeout", "6",
            "-H", f"Authorization: Key {api_key}",
            "-H", "Content-Type: application/json",
            "-d", body,
            "https://fal.run/fal-ai/flux/schnell",
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=38)
        if result.returncode != 0:
            raise OSError(f"curl error: {result.stderr.decode()[:100]}")
        data = json.loads(result.stdout)
        images = data.get("images", [])
        if images:
            url = images[0].get("url", "")
            if url:
                print(f"🎨 FAL Flux: сгенерировали фото → {url[:60]}...")
                return url
    except Exception as e:
        print(f"⚠️ FAL Flux ошибка: {e}")
    return None


def generate_imagen(keywords: str, api_key: str, proxy: str = "") -> str | None:
    """
    Генерация через Google Imagen 4.0 Fast.
    Требует US-прокси (Google API заблокирован для RU-аккаунтов).
    Возвращает путь к локальному файлу (не URL).
    """
    if not api_key:
        return None
    try:
        prompt = f"Professional realistic photograph: {keywords}. Natural lighting, high quality, no text or watermarks."
        body = json.dumps({
            "instances": [{"prompt": prompt}],
            "parameters": {"sampleCount": 1, "aspectRatio": "16:9"},
        })
        cmd = [
            "curl", "-s",
            "--max-time", "30",
            "--connect-timeout", "8",
        ]
        # US-прокси обязателен для обхода гео-блокировки Google AI API
        if proxy:
            cmd += ["--proxy", proxy]
        cmd += [
            "-H", "Content-Type: application/json",
            "-d", body,
            f"https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-fast-generate-001:predict?key={api_key}",
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=38)
        if result.returncode != 0:
            raise OSError(f"curl error: {result.stderr.decode()[:100]}")
        data = json.loads(result.stdout)
        if "error" in data:
            raise OSError(f"API error: {data['error'].get('message','')[:150]}")
        predictions = data.get("predictions", [])
        if predictions:
            b64 = predictions[0].get("bytesBase64Encoded", "")
            if b64:
                import base64
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                tmp.write(base64.b64decode(b64))
                tmp.close()
                print(f"🎨 Imagen 4.0: сгенерировали фото ({os.path.getsize(tmp.name)//1024} KB)")
                return tmp.name  # Локальный путь — download_photo не нужен
    except Exception as e:
        print(f"⚠️ Imagen 4.0 ошибка: {e}")
    return None


# ─── Загрузка фото в VK ───────────────────────────────────────────────────────

def download_photo(url: str) -> str | None:
    """Скачивает фото во временный файл через curl с retry."""
    last_err = None
    for attempt in range(1, 4):
        try:
            suffix = ".png" if "png" in url.lower() else ".jpg"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.close()
            cmd = [
                "curl", "-s", "-L",
                "--max-time", "20",
                "--connect-timeout", "6",
                "-H", "User-Agent: Mozilla/5.0",
                "-o", tmp.name,
                url,
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=28)
            if result.returncode == 0 and os.path.getsize(tmp.name) > 100:
                return tmp.name
            os.unlink(tmp.name)
            last_err = result.stderr.decode()[:100]
        except Exception as e:
            last_err = str(e)
        if attempt < 3:
            import time; time.sleep(2)
    print(f"⚠️ Скачать фото не удалось после 3 попыток: {last_err}")
    return None


def upload_photo_to_vk(photo_path: str, vk_token: str, vk_group_id: str) -> str | None:
    """
    Загружает фото на VK сервер.
    3 попытки на VK API уровне — устойчив к rate limit и временным ошибкам.
    Постоянные ошибки (неверный токен, доступ) не ретраятся.
    """
    _PERMANENT_CODES = {5, 15, 121, 200, 201, 203, 214, 220, 221}

    for attempt in range(1, 4):
        try:
            # 1. Получаем URL для загрузки
            upload_data = _vk_api_call("photos.getWallUploadServer", {"group_id": vk_group_id}, vk_token)
            if "error" in upload_data:
                code = upload_data["error"].get("error_code", 0)
                msg = upload_data["error"]["error_msg"]
                if code in _PERMANENT_CODES:
                    print(f"❌ VK getWallUploadServer: {msg}")
                    return None
                print(f"⚠️ VK getWallUploadServer ({code}), попытка {attempt}")
                if attempt < 3:
                    time.sleep(3)
                continue
            upload_url = upload_data["response"]["upload_url"]

            # 2. Загружаем файл (3 retry внутри _curl_upload)
            upload_result = json.loads(
                _curl_upload(upload_url, "photo", photo_path, timeout=30)
            )
            if not upload_result.get("photo"):
                print(f"⚠️ VK upload: пустой ответ, попытка {attempt}")
                if attempt < 3:
                    time.sleep(3)
                continue

            # 3. Сохраняем фото
            save_result = _vk_api_call("photos.saveWallPhoto", {
                "group_id": vk_group_id,
                "photo": upload_result["photo"],
                "server": upload_result["server"],
                "hash": upload_result["hash"],
            }, vk_token)

            if "error" in save_result:
                code = save_result["error"].get("error_code", 0)
                msg = save_result["error"]["error_msg"]
                if code in _PERMANENT_CODES:
                    print(f"❌ VK saveWallPhoto: {msg}")
                    return None
                print(f"⚠️ VK saveWallPhoto ({code}), попытка {attempt}")
                if attempt < 3:
                    time.sleep(3)
                continue

            photos = save_result.get("response", [])
            if not photos:
                print(f"⚠️ VK saveWallPhoto: пустой ответ, попытка {attempt}")
                if attempt < 3:
                    time.sleep(3)
                continue

            p = photos[0]
            attachment = f"photo{p['owner_id']}_{p['id']}"
            print(f"✅ Фото загружено в VK: {attachment}")

            return attachment

        except Exception as e:
            print(f"⚠️ Ошибка загрузки фото (попытка {attempt}): {e}")
            if attempt < 3:
                time.sleep(3)

    return None


# ─── Основная функция каскада ─────────────────────────────────────────────────

def get_photo_attachment(
    keywords: str,
    vk_token: str,
    vk_group_id: str,
    env: dict = None,
    group: str = ""
) -> str:
    """
    Каскадный поиск фото и загрузка в VK.
    1. Сначала проверяем локальный кеш (photo_cache.json) — для VPS
    2. Unsplash → Pexels → Pixabay — для локального запуска
    Возвращает attachment строку ('photo-123_456') или '' если ничего не нашли.
    """
    if env is None:
        env = load_env()

    # ── Шаг 0: Проверяем кеш (photo_cache.json) ──────────────────────────────
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_file = os.path.join(base_dir, "data", "photo_cache.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
            # Ищем по группе и ключевым словам
            cache_key = f"{group}::{keywords.lower().strip()}" if group else keywords.lower().strip()
            # Точное совпадение
            if cache_key in cache and cache[cache_key]:
                print(f"💾 Кеш: нашли фото для «{keywords}» → {cache[cache_key]}")
                return cache[cache_key]
            # Поиск без группы-префикса
            for k, v in cache.items():
                if keywords.lower().strip() in k and v:
                    print(f"💾 Кеш (частичное): «{keywords}» → {v}")
                    return v
        except Exception as e:
            print(f"⚠️ Кеш недоступен: {e}")

    # ── Шаг 1-3: Прямые запросы к API ────────────────────────────────────────
    unsplash_key = env.get("UNSPLASH_ACCESS_KEY", "")
    pexels_key = env.get("PEXELS_API_KEY", "")
    pixabay_key = env.get("PIXABAY_API_KEY", "")

    print(f"\n🔍 Ищем фото для: «{keywords}»")
    print(f"   Unsplash: {'✅' if unsplash_key else '❌ нет ключа'} | "
          f"Pexels: {'✅' if pexels_key else '❌ нет ключа'} | "
          f"Pixabay: {'✅' if pixabay_key else '❌ нет ключа'}")

    photo_url = None
    source = None

    for fetcher, key, name in [
        (fetch_unsplash, unsplash_key, "Unsplash"),
        (fetch_pexels, pexels_key, "Pexels"),
        (fetch_pixabay, pixabay_key, "Pixabay"),
    ]:
        if not key:
            continue
        photo_url = fetcher(keywords, key)
        if photo_url:
            source = name
            break

    if not photo_url:
        print("⚠️ Фото не найдено ни в одном источнике — публикуем без фото")
        return ""

    print(f"⬇️ Скачиваем с {source}...")
    photo_path = download_photo(photo_url)
    if not photo_path:
        print("⚠️ Не удалось скачать фото — публикуем без фото")
        return ""

    print("⬆️ Загружаем в VK...")
    attachment = upload_photo_to_vk(photo_path, vk_token, vk_group_id)
    return attachment or ""



# ─── CLI диагностика ──────────────────────────────────────────────────────────

def cmd_test(keywords="цыплята бройлер"):
    env = load_env()
    print("\n═══════════════════════════════════")
    print("  📸 PHOTO CASCADE — ДИАГНОСТИКА")
    print("═══════════════════════════════════\n")

    unsplash_key = env.get("UNSPLASH_ACCESS_KEY", "")
    pexels_key = env.get("PEXELS_API_KEY", "")
    pixabay_key = env.get("PIXABAY_API_KEY", "")

    print("🔑 Ключи в .env:")
    print(f"   UNSPLASH_ACCESS_KEY: {'✅ ' + unsplash_key[:12] + '...' if unsplash_key else '❌ пусто'}")
    print(f"   PEXELS_API_KEY:      {'✅ ' + pexels_key[:12] + '...' if pexels_key else '❌ пусто'}")
    print(f"   PIXABAY_API_KEY:     {'✅ ' + pixabay_key[:12] + '...' if pixabay_key else '❌ пусто'}")

    print(f"\n📡 Тест каждого источника (запрос: «{keywords}»):\n")

    results = {}
    for fetcher, key, name in [
        (fetch_unsplash, unsplash_key, "Unsplash"),
        (fetch_pexels, pexels_key, "Pexels"),
        (fetch_pixabay, pixabay_key, "Pixabay"),
    ]:
        if not key:
            results[name] = "❌ нет ключа"
            print(f"  {name}: ❌ нет ключа в .env")
            continue
        url = fetcher(keywords, key)
        if url:
            results[name] = f"✅ OK → {url[:50]}..."
            print(f"  {name}: ✅ OK")
        else:
            results[name] = "❌ нет результата"
            print(f"  {name}: ❌ нет результата (ошибка или заблокирован)")

    print("\n📊 Итог:")
    for name, status in results.items():
        print(f"  {name}: {status}")

    # Загрузка в VK не тестируем здесь (нужны токены группы)
    print("\n✅ Диагностика завершена.")
    print("   Для теста загрузки в VK — используй get_photo_attachment() в постере.\n")


if __name__ == "__main__":
    keywords = "цыплята бройлер"
    for arg in sys.argv[1:]:
        if arg.startswith("--keywords="):
            keywords = arg.split("=", 1)[1]

    cmd_test(keywords)
