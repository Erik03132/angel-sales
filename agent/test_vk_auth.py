import os

import vk_api
from dotenv import load_dotenv

load_dotenv("ai-eggs/.env")

login = os.getenv("VK_LOGIN")
password = os.getenv("VK_PASS")

try:
    vk_session = vk_api.VkApi(login, password)
    vk_session.auth()
    vk = vk_session.get_api()
    print("✅ Auth successful!")
    print(f"User ID: {vk_session.token['user_id']}")
    print(f"Token: {vk_session.token['access_token']}")
except Exception as e:
    print(f"❌ Auth failed: {e}")
