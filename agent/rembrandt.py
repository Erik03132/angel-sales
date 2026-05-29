#!/usr/bin/env python3
"""
🎨 Rembrandt — Агент-Художник

Генерация тематических фото для статей через Leonardo.ai API.

Использование:
    python3 rembrandt.py --prompt "farm poultry chickens" --output photo.png

═══════════════════════════════════════════════════════════════════════════
LEONARDO.AI API — ИНСТРУКЦИЯ
═══════════════════════════════════════════════════════════════════════════

1. РЕГИСТРАЦИЯ:
   - Зайти на https://app.leonardo.ai/
   - Sign Up (Google/Email)
   - Подтвердить email

2. ПОЛУЧЕНИЕ API КЛЮЧА:
   - Войти в https://app.leonardo.ai/
   - Нажать на аватар (справа сверху)
   - Выбрать "API Keys" или "Settings → API"
   - Нажать "Create API Key"
   - Скопировать ключ (начинается с "leo_...")

3. ДОБАВИТЬ В .ENV:
   LEONARDO_API_KEY=leo_xxxxxxxxxxxxxxxxxxxxxxxxxxxx

4. ТАРИФЫ:
   - Free: 150 токенов/день (~150 изображений)
   - Apprentice: $10/мес (~1000 изображений)
   - Artisan: $24/мес (~3000 изображений)

5. API ENDPOINT:
   POST https://cloud.leonardo.ai/api/rest/v1/generations
   
   Параметры:
   - prompt: описание изображения
   - modelId: модель (например, "6bef9f1b-29cb-40c7-b9df-32b51c1f67d3" - Leonardo Phoenix)
   - width: 1024 (по умолчанию)
   - height: 1024 (по умолчанию)
   - num_images: 1
   
   Ответ:
   - generationId: ID генерации
   - status: "COMPLETE" | "PENDING"
   
   Получить фото:
   GET https://cloud.leonardo.ai/api/rest/v1/generations/{generationId}
   
   В ответе: generated_images[].url

6. МОДЕЛИ (modelId):
   - Leonardo Phoenix: 6bef9f1b-29cb-40c7-b9df-32b51c1f67d3 (лучшее качество)
   - Leonardo Diffusion XL: e71a1c2f-3432-4365-aa9a-58804c51051d
   - Absolute Reality: c61732db-3fac-48d1-9e9e-608fc27e7519

7. ЛИМИТЫ:
   - Free: 150 изображений/день (сбрасывается ежедневно)
   - Время генерации: 30-60 секунд

═══════════════════════════════════════════════════════════════════════════
"""

import os
import sys
import time

import requests

BASE_DIR = "/Users/igorvasin/freelance-2026"
sys.path.insert(0, os.path.join(BASE_DIR, "ai-eggs", "agent"))

# ─── Загрузка .env ────────────────────────────────────────────────────────────

def load_env():
    env = {}
    env_path = os.path.join(BASE_DIR, "ai-eggs", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    return env

ENV = load_env()
LEONARDO_API_KEY = ENV.get("LEONARDO_API_KEY", "")
PROXY = ENV.get("TELEGRAM_PROXY", "")

# ─── Leonardo.ai API ──────────────────────────────────────────────────────────

LEONARDO_BASE_URL = "https://cloud.leonardo.ai/api/rest/v1"

# Модели Leonardo.ai
LEONARDO_MODELS = {
    "phoenix": "6bef9f1b-29cb-40c7-b9df-32b51c1f67d3",  # Leonardo Phoenix (лучшее)
    "diffusion_xl": "e71a1c2f-3432-4365-aa9a-58804c51051d",  # Leonardo Diffusion XL
    "absolute_reality": "c61732db-3fac-48d1-9e9e-608fc27e7519",  # Absolute Reality
}

def leonardo_generate(prompt: str, model: str = "phoenix", width: int = 1024, height: int = 1024) -> str | None:
    """
    Генерация изображения через Leonardo.ai API.
    
    prompt: описание изображения
    model: "phoenix" | "diffusion_xl" | "absolute_reality"
    width, height: размер (1024 по умолчанию)
    
    Возвращает URL изображения или None.
    """
    if not LEONARDO_API_KEY:
        print("❌ LEONARDO_API_KEY не найден в .env!")
        print("   Инструкция: см. docstring в начале файла rembrandt.py")
        return None
    
    model_id = LEONARDO_MODELS.get(model, LEONARDO_MODELS["phoenix"])
    
    headers = {
        "Authorization": f"Bearer {LEONARDO_API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "prompt": prompt,
        "negative_prompt": "text, watermark, signature, blurry, deformed, ugly, duplicate",
        "modelId": model_id,
        "width": width,
        "height": height,
        "num_images": 1,
        "scheduler": "EULER_DISCRETE",
        "sd_version": "SDXL_1_0",
    }
    
    print(f"   🎨 Leonardo.ai ({model})...")
    
    try:
        # Шаг 1: Запуск генерации
        response = requests.post(
            f"{LEONARDO_BASE_URL}/generations",
            headers=headers,
            json=payload,
            timeout=60,
        )
        
        data = response.json()
        
        if "sdGenerationJob" not in data:
            print(f"   ❌ Ошибка API: {data.get('error', {}).get('message', 'Unknown error')}")
            return None
        
        generation_id = data["sdGenerationJob"]["generationId"]
        print(f"   ⏳ Генерация... (ID: {generation_id[:8]}...)")
        
        # Шаг 2: Ожидание завершения (polling)
        max_attempts = 20
        for attempt in range(max_attempts):
            time.sleep(3)
            
            status_response = requests.get(
                f"{LEONARDO_BASE_URL}/generations/{generation_id}",
                headers=headers,
                timeout=30,
            )
            
            status_data = status_response.json()
            status = status_data.get("sdGenerationJob", {}).get("status", "PENDING")
            
            if status == "COMPLETE":
                print("   ✅ Готово!")
                
                # Получаем URL изображения
                generated_images = status_data.get("generated_images", [])
                if generated_images:
                    image_url = generated_images[0].get("url")
                    if image_url:
                        print(f"   📸 URL: {image_url[:80]}...")
                        return image_url
                else:
                    print("   ❌ Нет изображений в ответе")
                    return None
            
            elif status == "FAILED":
                print("   ❌ Генерация не удалась")
                return None
            
            else:
                print(f"   ⏳ Ожидание... ({attempt+1}/{max_attempts})")
        
        print("   ⏱️ Таймаут ожидания")
        return None
    
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return None


def download_image(url: str, output_path: str) -> bool:
    """Скачивает изображение по URL."""
    proxies = {}
    if PROXY:
        proxies = {"https": PROXY.replace("socks5://", "socks5h://"), "http": PROXY.replace("socks5://", "socks5h://")}
    
    try:
        response = requests.get(url, timeout=60, proxies=proxies if PROXY else None)
        
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            
            size = os.path.getsize(output_path) / 1024
            print(f"   💾 Сохранено: {output_path} ({size:.1f} KB)")
            return True
        else:
            print(f"   ❌ Ошибка скачивания: {response.status_code}")
            return False
    
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return False


# ─── Основной интерфейс ───────────────────────────────────────────────────────

def generate_photo(prompt: str, output_path: str = None, model: str = "phoenix") -> str | None:
    """
    Генерация и сохранение фото через Leonardo.ai.
    
    prompt: описание изображения
    output_path: путь для сохранения
    model: "phoenix" | "diffusion_xl" | "absolute_reality"
    
    Возвращает путь к файлу или None.
    """
    import tempfile
    
    if not output_path:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        output_path = tmp.name
        tmp.close()
    
    # Генерация через Leonardo
    image_url = leonardo_generate(prompt, model)
    
    if not image_url:
        return None
    
    # Скачивание
    if download_image(image_url, output_path):
        return output_path
    else:
        return None


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="🎨 Rembrandt — генерация фото через Leonardo.ai",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
═══════════════════════════════════════════════════════════════
ПРИМЕРЫ:
  python3 rembrandt.py -p "farm poultry chickens" -o photo.png
  python3 rembrandt.py -p "Russian garden vegetables" --model phoenix
═══════════════════════════════════════════════════════════════
        """
    )
    parser.add_argument("--prompt", "-p", required=True, help="Описание изображения")
    parser.add_argument("--output", "-o", default=None, help="Путь для сохранения")
    parser.add_argument("--model", "-m", default="phoenix", choices=["phoenix", "diffusion_xl", "absolute_reality"], help="Модель Leonardo.ai")
    
    args = parser.parse_args()
    
    print("="*70)
    print("🎨 Rembrandt — Leonardo.ai генерация")
    print("="*70)
    print()
    
    result = generate_photo(args.prompt, args.output, args.model)
    
    if result:
        print(f"\n📸 Готово: {result}")
    else:
        print("\n❌ Не удалось сгенерировать фото")
        print()
        print("Проверьте:")
        print("  1. LEONARDO_API_KEY в .env")
        print("  2. Регистрация на https://app.leonardo.ai/")
        print("  3. API ключ в Settings → API Keys")
        sys.exit(1)
