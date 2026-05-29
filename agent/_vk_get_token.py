#!/usr/bin/env python3
"""Get VK user token via Android app credentials (not IP-bound)."""
import json, subprocess, urllib.parse, os, re

BASE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.dirname(BASE), ".env")

env = {}
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()

login = env.get("VK_LOGIN", "")
password = env.get("VK_PASS", "")

# VK Android app credentials (public)
client_id = "2274003"
client_secret = "hHbZxrka2uZ6jB1inYsH"
scope = "photos,wall,groups,offline"

url = f"https://oauth.vk.com/token?grant_type=password&client_id={client_id}&client_secret={client_secret}&username={urllib.parse.quote(login)}&password={urllib.parse.quote(password)}&scope={scope}&v=5.199"
cmd = ["curl", "-s", "-L", "--max-time", "15", url]
r = subprocess.run(cmd, capture_output=True, timeout=20)
data = json.loads(r.stdout)

if "access_token" in data:
    token = data["access_token"]
    uid = data.get("user_id")
    print(f"✅ TOKEN: {token[:30]}...{token[-10:]}")
    print(f"   User ID: {uid}")

    with open(ENV_PATH, "r") as f:
        content = f.read()
    if re.search(r"^VK_USER_TOKEN=.*", content, re.MULTILINE):
        content = re.sub(r"^VK_USER_TOKEN=.*", f"VK_USER_TOKEN={token}", content, flags=re.MULTILINE)
    else:
        content += f"\nVK_USER_TOKEN={token}\n"
    with open(ENV_PATH, "w") as f:
        f.write(content)
    print("   ✅ Сохранён в .env")
else:
    print(f"❌ Ошибка: {data.get('error_description', data.get('error', '?'))}")
