#!/usr/bin/env python3
"""Get Mango call stats for today's batch autodial."""
import os, json, hashlib, requests, time
from dotenv import load_dotenv
load_dotenv("/root/antigravity/ai-eggs/.env", override=True)
for v in ("HTTPS_PROXY","HTTP_PROXY","ALL_PROXY","https_proxy","http_proxy","all_proxy"):
    os.environ.pop(v, None)
KEY = os.getenv("MANGO_VPBX_API_KEY")
SALT = os.getenv("MANGO_VPBX_API_SALT")

def sign(jd):
    j = json.dumps(jd, separators=(",",":"), ensure_ascii=False)
    return hashlib.sha256((KEY+j+SALT).encode()).hexdigest()

def api(ep, jd):
    j = json.dumps(jd, separators=(",",":"), ensure_ascii=False)
    return requests.post("https://app.mango-office.ru/vpbx/" + ep,
        data={"vpbx_api_key": KEY, "json": j, "sign": sign(jd)}, timeout=30)

from datetime import datetime
from_ts = int(datetime(2026,6,12,10,50).timestamp())
to_ts = int(datetime(2026,6,12,15,0).timestamp())

jd = {"date_from": from_ts, "date_to": to_ts, "from": {"extension": "22"},
      "fields": "start,finish,from_number,to_number,disconnect_reason,entry_id,talk_duration"}
r1 = api("stats/request", jd)
print("Request:", r1.text[:200])
key_val = r1.json().get("key","")
if key_val:
    for i in range(8):
        time.sleep(4)
        r2 = api("stats/result", {"key": key_val})
        ct = r2.headers.get("content-type","")
        print("Attempt %d: status=%d ct=%s len=%d" % (i+1, r2.status_code, ct, len(r2.text)))
        if r2.status_code == 200 and len(r2.text) > 10:
            print(r2.text[:8000])
            break
