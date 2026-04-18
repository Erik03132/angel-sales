import os
import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

BITRIX_URL = os.getenv("BITRIX_WEBHOOK_URL", "").rstrip("/")

for msg_id in [2279266, 2279268]:
    resp = requests.post(f"{BITRIX_URL}/im.message.delete.json", json={"MESSAGE_ID": msg_id})
    print(f"Delete {msg_id}: {resp.status_code} {resp.text}")
