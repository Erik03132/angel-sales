import os

import requests
from dotenv import load_dotenv

load_dotenv()

BITRIX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")

def check_comments():
    print("🔍 Проверка комментариев в ленте...")
    resp = requests.get(f"{BITRIX_URL}/log.blogpost.get.json")
    posts = resp.json().get("result", [])
    
    for post in posts:
        if "ПТЕНЧИКОВА" in (post.get("BLOG_TITLE") or "") or "ПТЕНЧИКОВА" in (post.get("DETAIL_TEXT") or ""):
            post_id = post["ID"]
            print(f"\n📢 Пост ID {post_id}: {post.get('BLOG_TITLE')}")
            
            c_resp = requests.get(f"{BITRIX_URL}/log.blogpost.getcomments.json", params={"POST_ID": post_id})
            comments = c_resp.json().get("result", [])
            
            if not comments:
                print("   (комментариев нет)")
            for c in comments:
                author = c.get("AUTHOR_NAME")
                text = c.get("POST_TEXT")
                print(f"   💬 {author}: {text}")

if __name__ == "__main__":
    check_comments()
