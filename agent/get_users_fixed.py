import os

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

bitrix_url = os.getenv("BITRIX_WEBHOOK_URL")
if not bitrix_url:
    print("NO WEBHOOK")
else:
    r = requests.get(f"{bitrix_url.rstrip('/')}/user.get")
    users = r.json().get("result", [])
    for u in users:
        print(f"ID: {u.get('ID')}, NAME: {u.get('NAME')} {u.get('LAST_NAME')}")
