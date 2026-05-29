#!/usr/bin/env python3
"""Test play/start with from.number parameter."""
import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv

for p in ['HTTPS_PROXY','HTTP_PROXY','ALL_PROXY']:
    os.environ.pop(p, None)

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env', override=True)

for p in ['HTTPS_PROXY','HTTP_PROXY','ALL_PROXY']:
    os.environ.pop(p, None)

KEY = os.getenv('MANGO_VPBX_API_KEY')
SALT = os.getenv('MANGO_VPBX_API_SALT')
AID = int(os.getenv('MANGO_AUDIO_ID', '1000550940'))

def api(endpoint, jd):
    j = json.dumps(jd, separators=(',',':'), ensure_ascii=False)
    sign = hashlib.sha256((KEY+j+SALT).encode()).hexdigest()
    r = requests.post(
        f'https://app.mango-office.ru/vpbx/{endpoint}',
        data={'vpbx_api_key':KEY,'json':j,'sign':sign},
        timeout=15,
    )
    return r.json()

if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} <call_id> [from_number]")
    sys.exit(1)

call_id = sys.argv[1]
client_num = sys.argv[2] if len(sys.argv) > 2 else ""

cmd1 = f'tp1_{uuid.uuid4().hex[:8]}'
r1 = api('play/start', {
    'command_id': cmd1,
    'call_id': call_id,
    'internal_id': AID,
})
print('NO-FROM:', r1)

if client_num:
    time.sleep(1)
    cmd2 = f'tp2_{uuid.uuid4().hex[:8]}'
    r2 = api('play/start', {
        'command_id': cmd2,
        'call_id': call_id,
        'internal_id': AID,
        'from': {'number': client_num},
    })
    print('FROM-CLIENT:', r2)
