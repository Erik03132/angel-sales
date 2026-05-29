#!/usr/bin/env python3
"""call_collector.py – собирает новые звонки через VoxImplant и сохраняет аудио.

Требования:
- .env с BITRIX_TOKEN, BITRIX_USER_ID (опционально) и другими переменными.
- Папка ./new_recordings/ будет хранить загруженные файлы WAV.
- Файл .last_processed_ts хранит метку UNIX‑времени последнего обработанного звонка.
"""

import os
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=ENV_PATH, override=True)

BITRIX_TOKEN = os.getenv("BITRIX24_TOKEN")
BITRIX_USER_ID = os.getenv("BITRIX24_USER_ID")  # optional, may be used for auth header

API_URL = "https://{{your_bitrix_domain}}/rest/"

LAST_TS_FILE = BASE_DIR / "ai-eggs" / ".last_processed_ts"
RECORDINGS_DIR = BASE_DIR / "ai-eggs" / "new_recordings"
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

def load_last_ts() -> int:
    if LAST_TS_FILE.exists():
        try:
            return int(LAST_TS_FILE.read_text().strip())
        except Exception:
            return 0
    return 0

def save_last_ts(ts: int):
    LAST_TS_FILE.write_text(str(ts))

def api_call(method: str, params: dict):
    url = f"{API_URL}{method}?auth={BITRIX_TOKEN}"
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Bitrix error: {data['error']}")
    return data.get("result", {})

def fetch_new_calls(since_ts: int):
    # Получаем только звонки типа VOXIMPLANT_CALL (TYPE_ID=2)
    params = {
        "filter[TYPE_ID]": 2,
        "filter[>CALL_START_DATE]": since_ts,
        "order[CALL_START_DATE]": "ASC",
        "select[CALL_START_DATE]": "*",
        "select[RECORD_FILE_ID]": "*",
        "select[CALL_ID]": "*",
    }
    return api_call("voximplant.statistic.get", params)

def download_record(record_id: str, dest_path: Path):
    # Bitrix provides endpoint /rest/voximplant.recording.download?FILE_ID=...
    url = f"{API_URL}voximplant.recording.download?auth={BITRIX_TOKEN}&FILE_ID={record_id}"
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

def main():
    last_ts = load_last_ts()
    print(f"🔎 Last processed timestamp: {last_ts}")
    calls = fetch_new_calls(last_ts)
    if not calls:
        print("✅ No new calls.")
        return
    max_ts = last_ts
    for call in calls:
        call_id = call.get("CALL_ID")
        start_date = int(call.get("CALL_START_DATE", 0))
        record_id = call.get("RECORD_FILE_ID")
        if not record_id:
            continue
        if start_date > max_ts:
            max_ts = start_date
        filename = f"call_{call_id}_{record_id}.wav"
        dest = RECORDINGS_DIR / filename
        if dest.exists():
            continue
        try:
            download_record(record_id, dest)
            print(f"📥 Downloaded {filename}")
        except Exception as e:
            print(f"⚠️ Failed to download {record_id}: {e}")
    save_last_ts(max_ts)
    print(f"🗂 Updated last timestamp to {max_ts}")

if __name__ == "__main__":
    main()
