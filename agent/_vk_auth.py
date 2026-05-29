#!/usr/bin/env python3
"""Try to get a VK user token via various methods."""
import json
import os
import subprocess
import sys
import urllib.parse

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

def vk_call(method, params, token=None):
    if token:
        params["access_token"] = token
    params["v"] = "5.199"
    url = f"https://api.vk.com/method/{method}"
    cmd = ["curl", "-s", "--max-time", "15", url]
    for k, v in params.items():
        cmd += ["-d", f"{k}={urllib.parse.quote(str(v))}"]
    result = subprocess.run(cmd, capture_output=True, timeout=20)
    return json.loads(result.stdout)

# Method 1: Try login via old VK auth flow (grant_type=password)
login = env.get("VK_LOGIN", "")
password = env.get("VK_PASS", "")
token = env.get("VK_SERVICE_TOKEN", "")

cmd = [
    "curl", "-s", "-L", "--max-time", "15",
    f"https://oauth.vk.com/token?grant_type=password&client_id=54572099&username={urllib.parse.quote(login)}&password={urllib.parse.quote(password)}&scope=photos,wall,groups,offline&v=5.199"
]
result = subprocess.run(cmd, capture_output=True, timeout=20)
data = json.loads(result.stdout)
if "access_token" in data:
    print(f"✅ TOKEN: {data['access_token']}")
    print(f"   user_id: {data.get('user_id')}")
    sys.exit(0)
else:
    print(f"❌ Auth error: {data.get('error_description', data.get('error', '?'))}")

# Method 2: Try to re-auth the existing token
if env.get("VK_USER_TOKEN"):
    print("\nTrying to use existing token (IP-bound)...")
    r = vk_call("users.get", {}, token=env["VK_USER_TOKEN"])
    print(f"   Result: {r}")

# Method 3: No valid token available
print("\n⚠️ No way to get a valid user token from VPS.")
print("   User needs to generate token manually via browser.")
print("   Visit: https://vk.com/dev/tokens?app_id=54572099")
