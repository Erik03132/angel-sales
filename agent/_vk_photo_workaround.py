#!/usr/bin/env python3
"""Upload photo to VK group album using group token + direct CDN upload."""
import json, subprocess, urllib.parse, os, sys

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

SERVICE_TOKEN = env.get("VK_SERVICE_TOKEN", "")
GROUP_TOKEN = env.get("VK_PODVORYE_TOKEN", "")
GROUP_ID = env.get("VK_PODVORYE_GROUP_ID", "-238230663")
PHOTO_PATH = sys.argv[1] if len(sys.argv) > 1 else "/root/antigravity/ai-eggs/data/pending_posts/podvorye_20260528_141737.jpg"

def vk_call(method, params, token=GROUP_TOKEN):
    params["access_token"] = token
    params["v"] = "5.199"
    params.setdefault("group_id", GROUP_ID.lstrip("-"))
    url = f"https://api.vk.com/method/{method}"
    cmd = ["curl", "-s", "--max-time", "15", url]
    for k, v in params.items():
        cmd += ["-d", f"{k}={urllib.parse.quote(str(v))}"]
    r = subprocess.run(cmd, capture_output=True, timeout=20)
    return json.loads(r.stdout)

# Step 1: Get group photo albums
print("📸 Step 1: Get group albums...")
r = vk_call("photos.getAlbums", {"owner_id": GROUP_ID})
print(json.dumps(r, indent=2)[:400])

# Step 2: Try to get upload server for album
print("\n📸 Step 2: Get upload server...")
r = vk_call("photos.getUploadServer", {"album_id": "wall"})
print(json.dumps(r, indent=2)[:400])

# Step 3: Try saving wall photo
print("\n📸 Step 3: Try saveWallPhoto...")
r = vk_call("photos.saveWallPhoto", {
    "group_id": GROUP_ID.lstrip("-"),
    "photo": "test",
    "server": 1,
    "hash": "test",
})
print(json.dumps(r, indent=2)[:400])
