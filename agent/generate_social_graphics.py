#!/usr/bin/env python3
"""
🎨 Генерация обложек и аватаров для ВК/ОК групп через Imagen 4.0
Использует US SOCKS5 прокси для обхода GEO-блока.
"""

import base64
import json
import os
import subprocess
import sys

# Загружаем .env
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
env = {}
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()

API_KEY = env.get("GEMINI_API_KEY", "") or env.get("GEMINI_PRO_API_KEY", "")
PROXY = env.get("TELEGRAM_PROXY", "")  # socks5://user:pass@host:port
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "social")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def generate(prompt: str, filename: str, aspect_ratio: str = "16:9"):
    """Генерирует изображение через Imagen 4.0 и сохраняет в файл."""
    print(f"\n🎨 Генерирую: {filename} ({aspect_ratio})...")
    print(f"   Промпт: {prompt[:80]}...")

    body = json.dumps({
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1, "aspectRatio": aspect_ratio},
    })

    cmd = [
        "curl", "-s",
        "--max-time", "60",
        "--connect-timeout", "10",
    ]
    if PROXY:
        cmd += ["--proxy", PROXY]
    cmd += [
        "-H", "Content-Type: application/json",
        "-d", body,
        f"https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-fast-generate-001:predict?key={API_KEY}",
    ]

    result = subprocess.run(cmd, capture_output=True, timeout=70)
    if result.returncode != 0:
        print(f"   ❌ curl ошибка: {result.stderr.decode()[:200]}")
        return False

    data = json.loads(result.stdout)
    if "error" in data:
        print(f"   ❌ API ошибка: {data['error'].get('message', '')[:200]}")
        return False

    predictions = data.get("predictions", [])
    if not predictions:
        print("   ❌ Нет результатов")
        return False

    b64 = predictions[0].get("bytesBase64Encoded", "")
    if not b64:
        print("   ❌ Нет данных изображения")
        return False

    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(base64.b64decode(b64))

    size_kb = os.path.getsize(filepath) // 1024
    print(f"   ✅ Сохранено: {filepath} ({size_kb} KB)")
    return True


# ═══ ПРОМПТЫ ═══

IMAGES = [
    {
        "filename": "vezemcip_cover.png",
        "aspect_ratio": "16:9",  # Ближайшее к 1944x600 (~3.24:1)
        "prompt": (
            "Wide panoramic banner for a poultry delivery business. "
            "NO TEXT, NO WORDS, NO LETTERS. "
            "Warm, inviting scene: golden sunrise over a green farm landscape "
            "with fluffy yellow baby chicks in the foreground, "
            "a delivery truck silhouette in the background, "
            "rolling green hills, blue sky with soft clouds. "
            "Professional quality, photorealistic style. "
            "Warm golden-orange and green color palette. Clean and premium feeling."
        ),
    },
    {
        "filename": "vezemcip_avatar.png",
        "aspect_ratio": "1:1",
        "prompt": (
            "Square avatar icon for a poultry delivery company. "
            "NO TEXT, NO WORDS, NO LETTERS. "
            "Cute fluffy yellow baby chick standing proudly, "
            "warm golden background with subtle sunburst rays. "
            "Simple, bold, recognizable at small sizes. "
            "Clean professional style, warm colors golden yellow and orange accents. "
            "The chick should be the clear focal point, centered composition. "
            "Modern logo-style illustration."
        ),
    },
    {
        "filename": "podvorye_cover.png",
        "aspect_ratio": "16:9",
        "prompt": (
            "Wide panoramic banner for a rural homesteading community about poultry keeping. "
            "NO TEXT, NO WORDS, NO LETTERS. "
            "Cozy rural scene: a beautiful wooden farmyard with chickens "
            "of different breeds freely roaming, a rustic wooden fence, "
            "garden with sunflowers, a charming countryside cottage in the background, "
            "warm afternoon light. "
            "Earthy natural color palette: warm browns, greens, golden light. "
            "Photorealistic style. Feels like home, welcoming and authentic."
        ),
    },
    {
        "filename": "podvorye_avatar.png",
        "aspect_ratio": "1:1",
        "prompt": (
            "Square avatar icon for a rural homesteading community. "
            "NO TEXT, NO WORDS, NO LETTERS. "
            "A proud rooster standing on a wooden fence post, sunrise behind. "
            "Warm earthy colors: brown, green, golden orange. "
            "Folk-art inspired style but modern and clean. "
            "Simple composition, recognizable at small sizes. "
            "The rooster is the clear focal point, centered. "
            "Rustic but premium quality illustration."
        ),
    },
]


if __name__ == "__main__":
    print("═" * 50)
    print("  🎨 ГЕНЕРАЦИЯ ОБЛОЖЕК И АВАТАРОВ ВК/ОК")
    print("═" * 50)
    print(f"  API Key: {API_KEY[:12]}..." if API_KEY else "  ❌ GEMINI_PRO_API_KEY не найден!")
    print(f"  Proxy: {PROXY[:30]}..." if PROXY else "  ⚠️ PROXY не найден")
    print(f"  Выход: {OUTPUT_DIR}")
    print()

    if not API_KEY:
        print("❌ Нет API ключа. Проверь GEMINI_PRO_API_KEY в .env")
        sys.exit(1)

    success = 0
    for img in IMAGES:
        if generate(img["prompt"], img["filename"], img["aspect_ratio"]):
            success += 1

    print(f"\n{'═' * 50}")
    print(f"  📊 ИТОГО: {success}/{len(IMAGES)} изображений сгенерировано")
    print(f"  📁 Файлы: {OUTPUT_DIR}")
    print(f"{'═' * 50}")
