import os

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

BITRIX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")
ANGELA_ID = 15

def update_live_feed():
    print("Публикация отчета в Живую Ленту...")
    post_text = (
        "💡 **Мастерская контента: Шекспир в деле!** 💡\n\n"
        "Пишу с отличными новостями. Наш копирайтер Шекспир полностью завершил создание контента первой очереди для канала Яндекс Дзен и ВКонтакте.\n\n"
        "Мы подготовили три убойные статьи, которые отвечают на 80% болей начинающих фермеров. Все они основаны на нашей базе знаний и скриптах:\n"
        "1. 🔥 **5 фатальных ошибок при покупке цыплят** (закрывает возражения и боль неопытности).\n"
        "2. ⚖️ **КОББ-500 или РОСС-308: Кого выбрать?** (помогает определиться с заказом).\n"
        "3. 🌾 **Чем кормить суточного бройлера** (нативно продаем наш комбикорм Purina/Energy и вет-аптечку за 200₽).\n\n"
        "Таким образом, мы закрываем в Битриксе третью, самую креативную задачу из нашего плана Продвижения! Статьи готовы, отформатированы и ждут только публикации, как только появятся доступы. 🚀"
    )
    try:
        resp = requests.post(f"{BITRIX_URL}/log.blogpost.add.json", json={
            "POST_TITLE": "Контент готов! Задача по копирайтингу закрыта.",
            "POST_MESSAGE": post_text,
            "DEST": ["UA"] 
        }, timeout=15)
        print("✅ Пост о контенте опубликован.")
    except Exception as e:
        print("Ошибка сети:", str(e))

def complete_content_task():
    print("\nПоиск задачи для закрытия...")
    try:
        resp = requests.post(f"{BITRIX_URL}/tasks.task.list.json", json={
            "filter": {"RESPONSIBLE_ID": ANGELA_ID, "<STATUS": 5}
        }, timeout=15)
        
        tasks_data = resp.json().get("result", {}).get("tasks", [])
        
        for task in tasks_data:
            if "Я.Дзен и ВК" in task["title"] or "Дзен" in task["title"]:
                task_id = task["id"]
                print(f"Найдена задача: {task['title']} (ID {task_id})")
                
                requests.post(f"{BITRIX_URL}/task.commentitem.add.json", json={
                    "TASKID": task_id,
                    "FIELDS": {
                        "AUTHOR_ID": ANGELA_ID, 
                        "POST_MESSAGE": "✅ Шекспир написал все 3 статьи! Тексты сохранены в системе (`ai-eggs/seo/content/`). Задача выполнена. Если нужны корректировки — скажите, Шекспир перепишет за 15 секунд."
                    }
                })
                
                requests.post(f"{BITRIX_URL}/tasks.task.complete.json", json={"taskId": task_id})
                print(f"✅ Задача [ID {task_id}] закрыта!")
                return
        
        print("Активная задача по контенту не найдена (возможно, уже была закрыта).")
    except Exception as e:
        print("Ошибка сети:", str(e))

if __name__ == "__main__":
    update_live_feed()
    complete_content_task()
