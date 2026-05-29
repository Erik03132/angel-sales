import json
import os
import re

# Подгружаем ядро Птенчиковой
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from angelochka_core import get_answer

load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

BITRIX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")
PTENCHIKOVA_ID = 15

# Хранилище обработанных ID комментариев (в памяти для простоты, можно в файл)
PROCESSED_COMMENTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "processed_feed_comments.json")

def load_processed_comments():
    if os.path.exists(PROCESSED_COMMENTS_FILE):
        try:
            with open(PROCESSED_COMMENTS_FILE, 'r') as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_processed_comments(processed_set):
    os.makedirs(os.path.dirname(PROCESSED_COMMENTS_FILE), exist_ok=True)
    with open(PROCESSED_COMMENTS_FILE, 'w') as f:
        json.dump(list(processed_set), f)

def get_recent_posts():
    try:
        resp = requests.get(f"{BITRIX_URL}/log.blogpost.get.json", timeout=15)
        return resp.json().get("result", [])
    except:
        return []

def get_comments(post_id):
    try:
        resp = requests.get(f"{BITRIX_URL}/log.blogpost.getcomments.json", params={"POST_ID": post_id}, timeout=15)
        return resp.json().get("result", [])
    except:
        return []

def add_comment(post_id, text):
    try:
        resp = requests.post(f"{BITRIX_URL}/log.blogpost.addcomment.json", json={
            "POST_ID": post_id,
            "TEXT": text
        }, timeout=15)
        return resp.json()
    except:
        return {}

def run_interaction():
    processed_comments = load_processed_comments()
    print(f"[{datetime.now()}] 🐥 Анжела Птенчикова сканирует Живую ленту...")
    
    posts = get_recent_posts()
    new_replies = 0

    for post in posts:
        post_id = post["ID"]
        # Условие: она автор, или это пост её коллег (Шекспир, Маркетолог и т.п.), либо она упомянута
        post_title = (post.get("TITLE") or "").upper()
        post_text = (post.get("DETAIL_TEXT") or "").upper()
        
        team_keywords = ["ПТЕНЧИКОВ", "ШЕКСПИР", "МАРКЕТОЛОГ", "РЕМБРАНДТ"]
        is_relevant = (str(post.get("AUTHOR_ID")) == str(PTENCHIKOVA_ID) or 
                       any(k in post_title for k in team_keywords) or 
                       "ПТЕНЧИКОВ" in post_text)
        
        # Теперь мы проверяем комменты ВО ВСЕХ недавних постах
        comments = get_comments(post_id)
        if comments:
            for comment in comments:
                cid = str(comment.get("ID"))
                author_id = str(comment.get("AUTHOR_ID"))
                
                # Игнорируем свои же новости (ID=15) и ответы вебхука (ID=1), а также уже обработанные
                if author_id in (str(PTENCHIKOVA_ID), "1") or cid in processed_comments:
                    continue
                
                author_name = comment.get("AUTHOR_NAME", "Бро")
                raw_text = comment.get("POST_TEXT", "")
                # Чистим текст от BB-кодов
                clean_text = re.sub(r'\[.*?\]', '', raw_text).strip()
                
                if not clean_text:
                    processed_comments.add(cid)
                    continue

                # УСЛОВИЕ РЕАКЦИИ:
                # 1. Либо пост релевантный (от её имени/צוותa)
                # 2. Либо в самом комментарии к ней обращаются (Анжела, Птенчикова)
                comment_mentions_her = bool(re.search(r'(анжел|птенчиков)', clean_text.lower()))
                
                if not (is_relevant or comment_mentions_her):
                    # Пропускаем коммент, если пост не её и её не позвали
                    continue

                print(f"🎯 Новый релевантный коммент от {author_name} под постом {post_id}: {clean_text[:50]}...")
                
                # ЛОГИКА ОДОБРЕНИЯ КОНТЕНТА
                text_up = clean_text.upper()
                # Ищем целые слова или фразы
                is_approved = ("ОДОБРЯЮ" in text_up or "В РАБОТУ" in text_up or 
                               "ОДОБРЕНО" in text_up or "ПУБЛИКУЙ" in text_up or 
                               bool(re.search(r'\bОК\b|\bOK\b', text_up)))
                
                if is_approved:
                    print(f"🚀 Получено ОДОБРЕНИЕ от {author_name}! Запускаю выкладку на Диск...")
                    try:
                        from bitrix_disk_manager import BitrixDiskManager
                        draft_path = os.path.join(BASE_DIR, 'data', 'content_drafts', 'last_draft.json')
                        if os.path.exists(draft_path):
                            with open(draft_path, 'r', encoding='utf-8') as f:
                                draft = json.load(f)
                            
                            disk = BitrixDiskManager()
                            root_id = disk.get_or_create_root_folder()
                            article_root = disk.create_subfolder(root_id, draft['folder_name'])
                            
                            mapping = {"zen": "01_DZEN", "vk": "02_VK", "ok": "03_OK", "max": "04_MAX", "industry": "05_ARCHIVE"}
                            for k, fbase in mapping.items():
                                if k in draft['content']:
                                    sub_id = disk.create_subfolder(article_root, fbase)
                                    ftext = str(draft['content'][k]) if not isinstance(draft['content'][k], dict) else json.dumps(draft['content'][k], ensure_ascii=False)
                                    disk.upload_file(sub_id, f"{k}_version.md", ftext)
                            
                            add_comment(post_id, f"✅ Принято, шеф! Все форматы статьи «{draft['topic']}» разложены по папкам на твоем Диске. Можешь проверять! 👋🐥")
                            processed_comments.add(cid)
                            continue
                        else:
                            add_comment(post_id, "⚠️ Ой, я не нашла черновик этой статьи в своей памяти... Видимо, он слишком старый.")
                    except Exception as ex:
                        print(f"❌ Ошибка при выкладке на диск: {ex}")
                        add_comment(post_id, "❌ Прости, возникла техническая ошибка при сохранении на Диск. Попробую еще раз позже!")

                # ОБЫЧНЫЙ ОТВЕТ ИИ (Только если позвали по имени)
                if comment_mentions_her:
                    feeed_prompt = f"Это комментарий от {author_name} под твоим постом в Живой ленте CRM. Ответь кратко, по-деловому, но в своем стиле. Если просят что-то сделать - подтверди.\n\nТекст комментария: {clean_text}"
                    
                    try:
                        # Генерируем ответ
                        response = get_answer(feeed_prompt, [])
                        
                        # Отправляем ответ
                        res = add_comment(post_id, response)
                        if "result" in res:
                            print(f"   ✅ Ответила! CID {cid} помечен как обработанный.")
                            processed_comments.add(cid)
                            new_replies += 1
                        else:
                            print(f"   ❌ Сбой при ответе: {res}")
                    except Exception as e:
                        print(f"   ❌ Ошибка ИИ-ядра: {e}")
                else:
                    # Комментарий не содержит ОК и не адресован Птенчиковой - просто помечаем как прочитанный
                    processed_comments.add(cid)

    if new_replies > 0:
        save_processed_comments(processed_comments)
    
    return new_replies

if __name__ == "__main__":
    # Запуск в режиме цикла (Polling для ленты)
    while True:
        try:
            run_interaction()
        except Exception as e:
            print(f"⚠️ Ошибка цикла ленты: {e}")
        
        # Раз в минуту проверяем ленту (чтобы не спамить запросами)
        time.sleep(60)
