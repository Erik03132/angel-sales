#!/usr/bin/env python3
"""
Генерация фото для постов в /ok/ за 3 дня (16, 17, 18 мая)
"""

import os
import re
import shutil
import sys

BASE_DIR = "/Users/igorvasin/freelance-2026"
OK_DIR = os.path.join(BASE_DIR, "ok")

sys.path.insert(0, os.path.join(BASE_DIR, "ai-eggs", "agent"))

from photo_cascade import (
    download_photo,
    fetch_pexels,
    fetch_unsplash,
    generate_imagen,
)


def load_env():
    env = {}
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    return env


def generate_photo_for_folder(folder_path: str, env: dict) -> bool:
    """Генерация фото для папки."""
    post_file = os.path.join(folder_path, "post.txt")
    photo_file = os.path.join(folder_path, "photo.png")
    
    if not os.path.exists(post_file):
        print("   ❌ post.txt не найден")
        return False
    
    if os.path.exists(photo_file):
        print("   ✅ Фото уже есть")
        return True
    
    # Читаем текст для ключевых слов
    with open(post_file, "r", encoding="utf-8") as f:
        post_text = f.read()
    
    # Извлекаем ключевые слова из первой строки
    first_line = post_text.split('\n')[0][:60]
    keywords = re.sub(r'[^\w\sа-яё]', '', first_line).strip()
    keywords = f"{keywords} farm poultry chickens"
    
    print(f"   🔑 Ключевые слова: {keywords[:50]}")
    
    # Каскад генерации
    photo_path = None
    
    # 1. Imagen 4.0
    gemini_key = env.get("GEMINI_API_KEY") or env.get("GEMINI_PRO_API_KEY")
    proxy = env.get("TELEGRAM_PROXY", "")
    
    if gemini_key and proxy:
        print("   🎨 Imagen 4.0...")
        try:
            photo_path = generate_imagen(keywords, gemini_key, proxy)
            if photo_path:
                print("   ✅ Imagen 4.0 успешно")
        except Exception as e:
            print(f"   ⚠️ Imagen ошибка: {e}")
    
    # 2. Unsplash fallback
    if not photo_path:
        unsplash_key = env.get("UNSPLASH_ACCESS_KEY", "")
        if unsplash_key:
            print("   📷 Unsplash...")
            try:
                url = fetch_unsplash(keywords, unsplash_key)
                if url:
                    photo_path = download_photo(url)
                    print("   ✅ Unsplash успешно")
            except Exception as e:
                print(f"   ⚠️ Unsplash ошибка: {e}")
    
    # 3. Pexels fallback
    if not photo_path:
        pexels_key = env.get("PEXELS_API_KEY", "")
        if pexels_key:
            print("   📷 Pexels...")
            try:
                url = fetch_pexels(keywords, pexels_key)
                if url:
                    photo_path = download_photo(url)
                    print("   ✅ Pexels успешно")
            except Exception as e:
                print(f"   ⚠️ Pexels ошибка: {e}")
    
    # 4. Pixabay fallback
    if not photo_path:
        pixabay_key = env.get("PIXABAY_API_KEY", "")
        if pixabay_key:
            print("   📷 Pixabay...")
            try:
                from photo_cascade import fetch_pixabay
                url = fetch_pixabay(keywords, pixabay_key)
                if url:
                    photo_path = download_photo(url)
                    print("   ✅ Pixabay успешно")
            except Exception as e:
                print(f"   ⚠️ Pixabay ошибка: {e}")
    
    # Сохраняем в папку
    if photo_path and os.path.exists(photo_path):
        shutil.copy2(photo_path, photo_file)
        print(f"   💾 Сохранено: {photo_file}")
        return True
    else:
        print("   ❌ Фото не сгенерировано")
        return False


def main():
    print("=== Генерация фото для /ok/ (16, 17, 18 мая) ===\n")
    
    env = load_env()
    
    dates = ["2026-05-16", "2026-05-17", "2026-05-18"]
    
    for date in dates:
        print(f"\n{date}:")
        
        # Ищем первую папку (_01)
        pattern = os.path.join(OK_DIR, f"{date}_01")
        
        if not os.path.exists(pattern):
            print("   ⚠️ Папка не найдена")
            continue
        
        folder_name = os.path.basename(pattern)
        print(f"   📁 {folder_name}:")
        
        success = generate_photo_for_folder(pattern, env)
        
        if success:
            print("   ✅ Готово")
        else:
            print("   ❌ Не удалось")
    
    print("\n=== Готово ===")


if __name__ == '__main__':
    main()
