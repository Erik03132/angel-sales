#!/usr/bin/env python3
"""Leonardo.ai — генерация 16 фото для Своё Подворье"""

import os
import time

import requests

BASE_DIR = "/Users/igorvasin/freelance-2026"
REVIEW_DIR = os.path.join(BASE_DIR, "НА_ПРОВЕРКУ_Своё_Подворье")
API_KEY = "2256cede-7124-473e-a1e3-a674d9652a74"
BASE_URL = "https://cloud.leonardo.ai/api/rest/v1"
MODEL = "6bef9f1b-29cb-40c7-b9df-32b51c1f67d3"  # Phoenix

folders_prompts = [
    ("16_05_2026_01_garden", "Russian vegetable garden May, raised beds tomatoes cucumbers, greenhouse, natural daylight, photorealistic, no text"),
    ("17_05_2026_02_rabbits", "Goat in modern farm barn, clean stable, brown white goat, natural lighting, photorealistic"),
    ("18_05_2026_03_poultry", "Baby chicks eating from feeder, first day, warm brooder light, closeup, photorealistic"),
    ("19_05_2026_04_bees", "Beehive on Russian homestead, beekeeper protective suit, honey frames, sunny, photorealistic"),
    ("20_05_2026_05_tips", "Farm tools layout, shovel rake gloves watering can, wooden background, top view, photorealistic"),
    ("21_05_2026_06_poultry", "Broiler chickens vs laying hens, split view, farm setting, photorealistic"),
    ("22_05_2026_07_bees", "Ducks geese on farm pond, waterfowl swimming, rural, natural lighting, photorealistic"),
    ("23_05_2026_08_tips", "Calculator notebook on farm ledger, profit calculation, rustic table, photorealistic"),
    ("24_05_2026_09_garden", "Garden pests natural remedies, garlic spray, eco friendly, photorealistic"),
    ("25_05_2026_10_rabbits", "Rabbit farm cages, clean modern rabbitry, white rabbits, photorealistic"),
    ("26_05_2026_11_poultry", "Russian chicken breeds, Rhode Island Red Orpington Leghorn, farm yard, photorealistic"),
    ("27_05_2026_12_bees", "Honey harvesting equipment, frames extractor, apiary tools, photorealistic"),
    ("28_05_2026_13_tips", "Poultry feed grains corn wheat, wooden bowls, farm, photorealistic"),
    ("29_05_2026_14_garden", "Greenhouse tomato cucumber, drip irrigation, May care, photorealistic"),
    ("30_05_2026_15_rabbits", "Fresh goat milk glass pitcher, cheese making, rustic kitchen, photorealistic"),
    ("31_05_2026_16_poultry", "Egg incubator comparison, two incubators side by side with eggs, photorealistic"),
]

headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
session = requests.Session()
start = time.time()

print("="*70)
print("🎨 Leonardo.ai Phoenix — 16 фото")
print("="*70)
print()

done = 0
for folder, prompt in folders_prompts:
    photo_file = os.path.join(REVIEW_DIR, folder, "photo.png")
    if os.path.exists(photo_file):
        print(f"⏭️ {folder}: готово")
        done += 1
        continue
    
    print(f"📸 {folder}... ", end="", flush=True)
    
    payload = {
        "prompt": prompt,
        "negative_prompt": "text, watermark, signature, blurry, deformed, ugly",
        "modelId": MODEL,
        "width": 1024, "height": 1024,
        "num_images": 1,
    }
    
    try:
        resp = session.post(f"{BASE_URL}/generations", headers=headers, json=payload, timeout=60)
        data = resp.json()
        
        if "sdGenerationJob" not in data:
            print(f"❌ {data.get('error', 'unknown')}")
            continue
        
        gen_id = data["sdGenerationJob"]["generationId"]
        
        for i in range(20):
            time.sleep(4)
            status = session.get(f"{BASE_URL}/generations/{gen_id}", headers=headers, timeout=30).json()
            
            if status.get("sdGenerationJob", {}).get("status") == "COMPLETE":
                imgs = status.get("generated_images", [])
                if imgs:
                    url = imgs[0].get("url")
                    img = session.get(url, timeout=60).content
                    with open(photo_file, "wb") as f:
                        f.write(img)
                    size = os.path.getsize(photo_file) / 1024
                    print(f"✅ {size:.0f}KB")
                    done += 1
                break
            elif status.get("sdGenerationJob", {}).get("status") == "FAILED":
                print("❌ FAILED")
                break
    except Exception as e:
        print(f"❌ {str(e)[:50]}")

elapsed = int(time.time() - start)
print()
print("="*70)
print(f"✅ ГОТОВО! Время: {elapsed}s ({elapsed/60:.1f} мин)")
print(f"Фото: {done}/16")
print("="*70)
