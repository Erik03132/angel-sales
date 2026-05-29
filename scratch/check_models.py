import os
from google import genai
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

print("🔍 Проверка доступных моделей...")
try:
    for model in client.models.list():
        print(f" - {model.name}")
except Exception as e:
    print(f"❌ Ошибка: {e}")
