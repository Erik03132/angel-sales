import os
import requests
from dotenv import load_dotenv

load_dotenv("/Users/igorvasin/freelance-2026/ai-eggs/.env")
KEY = os.getenv("OPENROUTER_API_KEY")

print(f"Key: {KEY[:10]}...")

resp = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={"Authorization": f"Bearer {KEY}"},
    json={
        "model": "google/gemini-2.0-flash-001",
        "messages": [{"role": "user", "content": "Say 'OK' if you see this."}]
    },
    proxies={"http": "", "https": ""},
    timeout=10
)

print(f"Status: {resp.status_code}")
print(f"Response: {resp.text}")
