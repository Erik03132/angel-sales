import os
import requests
import json
from dotenv import load_dotenv

BASE_DIR = "/Users/igorvasin/freelance-2026/ai-eggs"
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

SANDBOX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")

def check_sandbox():
    print(f"--- CHECKING SANDBOX TASKS ({SANDBOX_URL[:40]}...) ---")
    try:
        resp = requests.get(f"{SANDBOX_URL}/tasks.task.list.json", params={
            "select[]": ["ID", "TITLE", "STATUS", "CREATED_DATE"],
            "order[ID]": "DESC"
        })
        tasks = resp.json().get("result", {}).get("tasks", [])
        print(f"Found {len(tasks)} tasks:")
        for t in tasks[:10]:
            print(f"- [{t['ID']}] {t['TITLE']} (Status: {t['status']}, Created: {t['createdDate']})")
            
        print("\n--- CHECKING SANDBOX LIVE FEED ---")
        resp = requests.get(f"{SANDBOX_URL}/log.blogpost.get.json")
        posts = resp.json().get("result", [])
        print(f"Found {len(posts)} posts:")
        for p in posts[:3]:
             print(f"- {p.get('TITLE', 'No Title')} (Date: {p.get('DATE_PUBLISH')})")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_sandbox()
