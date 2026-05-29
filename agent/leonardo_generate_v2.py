#!/usr/bin/env python3
"""
Leonardo.ai — генерация 16 фото для «Своё Подворье» (V2 — Vision XL)

Изменения vs v1:
  - Модель: Vision XL (фотореализм) вместо Phoenix (стилизация)
  - Промпты: детальные, с указанием камеры, объектива, освещения
  - Negative prompt: полный блок антимутаций
  - Alchemy: включена для повышения качества
  - Пропуск уже существующих фото

Использование:
    python3 leonardo_generate_v2.py          # все 16 фото
    python3 leonardo_generate_v2.py --force  # перегенерить ВСЕ (включая существующие)
"""

import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Загрузка API ключа из .env
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
API_KEY = os.getenv("LEONARDO_API_KEY", "")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
REVIEW_DIR = BASE_DIR / "НА_ПРОВЕРКУ_Своё_Подворье"
BASE_URL = "https://cloud.leonardo.ai/api/rest/v1"

# Leonardo Vision XL — лучшая для фотореализма через API
MODEL_ID = "5c232a9e-9061-4777-980a-ddc8e65647c6"

# Универсальный negative prompt — блокирует мутации
NEGATIVE_PROMPT = (
    "text, watermark, logo, signature, stamp, "
    "deformed, mutated, extra limbs, extra legs, extra heads, extra fingers, "
    "ugly, bad anatomy, disfigured, malformed, "
    "blurry, low quality, pixelated, "
    "cartoon, illustration, drawing, painting, digital art, "
    "surreal, abstract, CGI, 3D render, anime, "
    "oversaturated, neon colors"
)

# === ПРОМПТЫ ДЛЯ КАЖДОГО ПОСТА ===
# Формат: (папка, промпт)
# Каждый промпт включает: ЧТО, ГДЕ, СВЕТ, КАМЕРА, СТИЛЬ
folders_prompts = [
    ("16_05_2026_01_garden",
     "Professional photograph of a beautiful Russian homestead vegetable garden in May. "
     "Neat raised wooden beds with young tomato and cucumber seedlings in rows. "
     "A small polycarbonate greenhouse in the background. Green grass paths between beds. "
     "Morning golden hour sunlight. Rural Russian countryside setting. "
     "Shot on Canon EOS R5, 35mm lens, f/5.6. Editorial magazine quality, warm tones."),

    ("17_05_2026_02_rabbits",
     "Professional editorial photograph for farming magazine. "
     "A beautiful healthy domestic dairy goat standing calmly inside a clean rustic wooden barn. "
     "Brown and white fur, gentle eyes, correct natural anatomy, two horns. "
     "Warm natural sunlight streams through the barn window. Clean straw bedding on floor. "
     "Shot on Canon EOS R5, 85mm lens, f/2.8, shallow depth of field. Warm color grading."),

    ("18_05_2026_03_poultry",
     "Close-up photograph of adorable fluffy yellow baby chicks in a warm brooder. "
     "Day-old chicks with soft yellow down feathers clustered around a small feed tray. "
     "Clean wood shavings bedding. Warm red heat lamp glow. "
     "Shot on Canon 5D Mark IV, 100mm macro, f/4. Shallow depth of field. "
     "Warm cozy atmosphere. Editorial quality, ultra detailed."),

    ("19_05_2026_04_bees",
     "Professional photograph of a beekeeper in white protective suit inspecting honey frames "
     "at a small apiary in a Russian countryside garden. Wooden beehives in a row. "
     "Bright sunny summer day, green trees in background. Bees visible on the frame. "
     "Shot on Canon EOS R5, 50mm, f/4. Natural lighting, warm editorial style."),

    ("20_05_2026_05_tips",
     "Flat lay photograph of essential farm and garden tools on a rustic wooden table. "
     "Garden gloves, pruning shears, small hand rake, twine, seed packets, watering can. "
     "Morning light from the side. Organized neat layout, top-down view. "
     "Shot on Canon 5D, 24mm, f/8. Clean editorial style, warm tones."),

    ("21_05_2026_06_poultry",
     "Professional photograph of a mixed flock of farm chickens in a green outdoor yard. "
     "White Leghorn hens and brown Rhode Island Red hens foraging on green grass. "
     "Wooden chicken coop in the background. Sunny day, natural light. "
     "Shot on Canon EOS R5, 70mm, f/4. Shallow depth of field. Farm lifestyle editorial."),

    ("22_05_2026_07_bees",
     "Beautiful photograph of domestic ducks and geese swimming on a calm farm pond. "
     "White geese and brown ducks in clear water with green reeds. "
     "Rural Russian countryside, willow trees, sunny afternoon. "
     "Shot on Canon EOS R5, 135mm, f/4. Reflection in water. Warm natural light."),

    ("23_05_2026_08_tips",
     "Still life photograph of a farmer's financial planning desk. "
     "Vintage notebook with handwritten calculations, old calculator, coffee mug. "
     "Stack of rubles bills, pen, reading glasses on a rustic wooden table. "
     "Warm morning window light. Shot on Canon 5D, 50mm, f/2.8. Cozy editorial style."),

    ("24_05_2026_09_garden",
     "Photograph of natural garden pest control methods on a rustic table. "
     "Glass spray bottle with garlic infusion, fresh garlic bulbs, dried herbs. "
     "Small potted tomato plant. Wooden background, natural daylight. "
     "Shot on Canon 5D, 50mm, f/4. Clean editorial food photography style."),

    ("25_05_2026_10_rabbits",
     "Professional photograph of a clean modern rabbit hutch on a Russian homestead. "
     "Cute white and grey domestic rabbits in spacious wire cages with wooden frames. "
     "Fresh hay and water bottles. Clean well-maintained rabbitry. Natural daylight. "
     "Shot on Canon EOS R5, 35mm, f/4. Warm editorial farming magazine quality."),

    ("26_05_2026_11_poultry",
     "Professional portrait of a majestic rooster standing proudly in a farmyard. "
     "Beautiful Rhode Island Red rooster with glossy red-brown feathers and bright red comb. "
     "Green grass, wooden fence in background, golden hour sunlight. "
     "Shot on Canon EOS R5, 85mm, f/2.8, shallow depth of field. Stunning detail."),

    ("27_05_2026_12_bees",
     "Close-up photograph of golden honey being extracted from a honeycomb frame. "
     "Beekeeper's uncapping fork revealing fresh honey cells. Golden amber honey dripping. "
     "Rustic wooden apiary workbench. Warm natural light. "
     "Shot on Canon 5D, 100mm macro, f/4. Ultra detailed, editorial food photography."),

    ("28_05_2026_13_tips",
     "Overhead photograph of various poultry feed grains in rustic wooden bowls. "
     "Golden wheat, yellow corn kernels, green peas, brown oats, sunflower seeds. "
     "Arranged on a dark wooden farmhouse table. Natural window light from above. "
     "Shot on Canon 5D, 24mm, f/8. Food photography style, warm earthy tones."),

    ("29_05_2026_14_garden",
     "Professional photograph inside a greenhouse with ripe red tomatoes on the vine. "
     "Lush green tomato plants with clusters of red and green tomatoes. Drip irrigation visible. "
     "Warm humid atmosphere, sunlight filtering through polycarbonate walls. "
     "Shot on Canon EOS R5, 35mm, f/4. Vibrant colors, editorial gardening magazine."),

    ("30_05_2026_15_rabbits",
     "Beautiful rustic still life of fresh goat milk and cheese. "
     "Glass pitcher of white creamy goat milk, round white goat cheese on wooden board. "
     "Fresh herbs, linen napkin on a farmhouse kitchen table. Morning window light. "
     "Shot on Canon 5D, 50mm, f/2.8. Food photography, warm pastoral style."),

    ("31_05_2026_16_poultry",
     "Professional photograph of a modern egg incubator with eggs inside. "
     "Digital incubator with glass window showing rows of white and brown chicken eggs. "
     "Temperature display visible. Clean lab-like setting with warm lighting. "
     "Shot on Canon 5D, 50mm, f/4. Product photography, clean editorial style."),
]


def generate_image(prompt: str, output_path: str) -> bool:
    """Генерация одного изображения через Leonardo Vision XL."""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "prompt": prompt,
        "negative_prompt": NEGATIVE_PROMPT,
        "modelId": MODEL_ID,
        "width": 1024,
        "height": 1024,
        "num_images": 1,
        "alchemy": True,
    }

    try:
        resp = requests.post(
            f"{BASE_URL}/generations", headers=headers, json=payload, timeout=60
        )
        data = resp.json()

        if "sdGenerationJob" not in data:
            print(f"  ❌ API error: {data}")
            return False

        gen_id = data["sdGenerationJob"]["generationId"]

        # Polling
        for i in range(30):
            time.sleep(4)
            status = requests.get(
                f"{BASE_URL}/generations/{gen_id}", headers=headers, timeout=30
            ).json()
            job = status.get("generations_by_pk", {})
            s = job.get("status", "UNKNOWN")

            if s == "COMPLETE":
                imgs = job.get("generated_images", [])
                if imgs:
                    url = imgs[0]["url"]
                    img = requests.get(url, timeout=60).content
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    with open(output_path, "wb") as f:
                        f.write(img)
                    size_kb = os.path.getsize(output_path) / 1024
                    print(f"  ✅ {size_kb:.0f}KB ({i*4}s)")
                    return True
                return False
            elif s == "FAILED":
                print("  ❌ Generation FAILED")
                return False

        print("  ❌ Timeout")
        return False

    except Exception as e:
        print(f"  ❌ {str(e)[:80]}")
        return False


def main():
    force = "--force" in sys.argv

    if not API_KEY:
        print("❌ LEONARDO_API_KEY не найден в .env!")
        print("   Добавьте: LEONARDO_API_KEY=your_key_here")
        return

    print("=" * 60)
    print("🎨 Leonardo Vision XL — 16 фото «Своё Подворье» (V2)")
    print("   Модель: Vision XL (фотореализм)")
    print("   Alchemy: ON")
    print(f"   Force: {force}")
    print("=" * 60)
    print()

    done = 0
    skipped = 0
    failed = 0
    start = time.time()

    for folder, prompt in folders_prompts:
        photo_file = str(REVIEW_DIR / folder / "photo.png")

        if os.path.exists(photo_file) and not force:
            # Сохраняем старое как backup
            print(f"⏭️  {folder}: уже есть (--force для перегенерации)")
            skipped += 1
            continue

        if os.path.exists(photo_file) and force:
            # Бэкапим старое
            backup = photo_file.replace("photo.png", "photo_old_phoenix.png")
            if not os.path.exists(backup):
                os.rename(photo_file, backup)

        print(f"📸 {folder}...", flush=True)
        if generate_image(prompt, photo_file):
            done += 1
        else:
            failed += 1

        # Пауза между генерациями (rate limit)
        time.sleep(2)

    elapsed = int(time.time() - start)
    print()
    print("=" * 60)
    print(f"📊 ИТОГО: {done} новых, {skipped} пропущено, {failed} ошибок")
    print(f"   Время: {elapsed}s ({elapsed / 60:.1f} мин)")
    print("=" * 60)


if __name__ == "__main__":
    main()
