import os
import sys
from datetime import datetime

BASE_DIR = "/Users/igorvasin/freelance-2026/ai-eggs"
sys.path.insert(0, os.path.join(BASE_DIR, "agent"))

from angelochka_core import _build_prompt_for_role

def verify_logic():
    print("--- DEBUG PROMPTS ---")
    
    os.environ["BITRIX_WEBHOOK_URL"] = "https://incubird.bitrix24.ru/rest/..."
    prompt_z = _build_prompt_for_role("creator", "менеджеры", "", "", "", "")
    print(f"\nPROMPT ZABOTKINA (first 600 chars):\n{prompt_z[:600]}")
    
    os.environ["BITRIX_WEBHOOK_URL"] = "https://b24-mjxvhq.bitrix24.ru/rest/1/..."
    prompt_p = _build_prompt_for_role("creator", "задачи", "", "", "", "")
    print(f"\nPROMPT PTENCHIKOVA (first 600 chars):\n{prompt_p[:600]}")

if __name__ == "__main__":
    verify_logic()
