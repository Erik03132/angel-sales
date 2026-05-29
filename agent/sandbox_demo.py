import os
import time

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

# Новый вебхук с полными правами
BITRIX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")
# ID Анжелы Птенчиковой в Песочнице
ANGELA_ID = 15

# 1. ПУБЛИКАЦИЯ В ЖИВУЮ ЛЕНТУ
def post_to_livefeed():
    print(f"Отправка поста в Живую Ленту от лица Анжелы (ID:{ANGELA_ID})...")
    post_text = (
        "🐥 **Всем привет! Это Анжела Птенчикова.**\n\n"
        "Мы переходим от теории к практике. Теперь я буду руководить нашим планом продвижения «IncuBird 2.0» "
        "и вести проекты в Битрикс24!\n\n"
        "Прямо сейчас я автоматически ставлю себе первые 3 задачи по [плану Продвижения VezemCip.ru], "
        "чтобы вы могли видеть мой прогресс в реальном времени. Если текст или картинка готовы — я буду прикреплять "
        "их в комментарии к задаче, а вам останется только нажать кнопку «Одобрить».\n\n"
        "Битрикс — это не только CRM для звонков. Это моё цифровое рабочее место! 🚀"
    )
    
    # К сожалению, REST API log.blogpost.add публикует от имени владельца вебхука (Igor Vasin - 1).
    # Но мы укажем в тексте, что это от Анжелы, и позже, когда у Анжелы будет свой аккаунт/токен, переключимся.
    # Так как webhook от ID 1 (Игорь), мы не можем подменить POSTER_ID в Живой ленте через обычный вебхук.
    # Однако мы можем упомянуть всех и поставить Анжелу автором задач!

    try:
        resp = requests.post(f"{BITRIX_URL}/log.blogpost.add.json", json={
            "POST_TITLE": "🚀 Переход к Автоматическому управлению (Анжела Птенчикова)",
            "POST_MESSAGE": post_text,
            "DEST": ["UA"] # Отправить всем сотрудникам (All Users)
        }, timeout=15)
        res = resp.json()
        if res.get("result"):
            print("✅ Пост в ленту успешно создан!")
        else:
            print("⚠️ Ошибка создания поста:", res)
    except Exception as e:
        print("Ошибка сети:", str(e))

# 2. СОЗДАНИЕ ЗАДАЧ
def create_promotion_tasks():
    tasks = [
        {
            "TITLE": "[ПРОМО] Аудит и ребрендинг группы ВК (ВезёмЦыплят)",
            "DESCRIPTION": "1. Проверить старую группу.\n2. Сделать новую обложку и аватар.\n3. Обновить описание с триплетами.",
            "DEADLINE": "2026-04-28T18:00:00",
            "TAGS": ["вк", "промо", "неделя-1"]
        },
        {
            "TITLE": "[ПРОМО] Создать и внедрить файл llms.txt на сайт",
            "DESCRIPTION": "Сайт должен быть понятен нейросетям (SearchGPT, Perplexity). Загрузить карту контента сайта.",
            "DEADLINE": "2026-04-30T18:00:00",
            "TAGS": ["сайт", "seo", "неделя-1"]
        },
        {
            "TITLE": "[ПРОМО] Написание 3 постов для Я.Дзен и ВК",
            "DESCRIPTION": "Адаптация экспертной базы знаний под 3 статьи:\n- 5 ошибок при покупке бройлеров\n- КОББ-500 или РОСС-308?\n- Кормление суточных цыплят.",
            "DEADLINE": "2026-05-01T18:00:00",
            "TAGS": ["контент", "копирайтинг"]
        }
    ]

    print("\nСоздание задач в Битрикс24...")
    for t in tasks:
        # Анжела сама себе ставит задачу и сама ответственна! 
        # (Так как вебхук от админа, он может ставить задачи от имени кого угодно на кого угодно)
        task_data = {
            "fields": {
                "TITLE": t["TITLE"],
                "DESCRIPTION": t["DESCRIPTION"],
                "CREATED_BY": ANGELA_ID,     # Кто поставил - Анжела!
                "RESPONSIBLE_ID": ANGELA_ID, # Кто выполняет - Анжела!
                "DEADLINE": t["DEADLINE"],
                "TAGS": t["TAGS"]
            }
        }
        
        try:
            resp = requests.post(f"{BITRIX_URL}/tasks.task.add.json", json=task_data, timeout=15)
            res = resp.json()
            if res.get("result"):
                task_id = res["result"]["task"]["id"]
                print(f"✅ Задача '{t['TITLE']}' создана (ID: {task_id}). Назначена на Анжелу (ID {ANGELA_ID}).")
                
                # Сразу делаем тестовый авто-отчет в комментариях!
                time.sleep(1)
                comment_resp = requests.post(f"{BITRIX_URL}/task.commentitem.add.json", json={
                    "TASKID": task_id,
                    "FIELDS": {
                        "AUTHOR_ID": ANGELA_ID, 
                        "POST_MESSAGE": "✅ Задача принята в работу! Шерлок уже начал собирать данные."
                    }
                })
            else:
                print(f"⚠️ Ошибка создания задачи '{t['TITLE']}':", res)
        except Exception as e:
            print("Ошибка сети:", str(e))


if __name__ == "__main__":
    print("🚀 Запуск ДЕМО Анжелы Птенчиковой в Песочнице Битрикс24")
    print(f"Используем вебхук: {BITRIX_URL}")
    post_to_livefeed()
    create_promotion_tasks()
    print("\n🎉 Готово! Можно идти проверять Живую Ленту и Задачи в Битриксе.")
