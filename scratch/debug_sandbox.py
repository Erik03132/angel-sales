import os
import requests
import json
from dotenv import load_dotenv

BASE_DIR = "/Users/igorvasin/freelance-2026/ai-eggs"
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

SANDBOX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")

def check_sandbox():
    try:
        resp = requests.get(f"{SANDBOX_URL}/tasks.task.list.json")
        data = resp.json()
        print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_sandbox()
