import base64
import os

import requests
from dotenv import load_dotenv

load_dotenv()

BITRIX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")
PTENCHIKOVA_FOLDER_ID = 89 # ROOT_OBJECT_ID для User 15

FILES_TO_UPLOAD = [
    {
        "path": "/Users/igorvasin/freelance-2026/ai-eggs/DAILY_ROADMAP_ANDREY.md",
        "name": "Глобальный_план_развития_IncuBird_2.0.md"
    },
    {
        "path": "/Users/igorvasin/freelance-2026/ai-eggs/angel-sales/docs/MASTER_PLAN_FULL_CYCLE.md",
        "name": "Маркетинговый_план_продвижения_IncuBird_2.0.md"
    }
]

def upload_file(file_path, file_name):
    with open(file_path, "rb") as f:
        file_content = base64.b64encode(f.read()).decode("utf-8")
    
    url = f"{BITRIX_URL}/disk.folder.uploadfile.json"
    params = {
        "id": PTENCHIKOVA_FOLDER_ID,
        "data": {"NAME": file_name},
        "fileContent": file_content
    }
    resp = requests.post(url, json=params)
    return resp.json()

if __name__ == "__main__":
    print("📂 Загрузка документов в ЛИЧНЫЙ раздел Птенчиковой...")
    for f in FILES_TO_UPLOAD:
        res = upload_file(f["path"], f["name"])
        if "result" in res:
            print(f"   ✅ Успешно! {f['name']}")
        else:
            print(f"   ❌ Ошибка: {res}")
