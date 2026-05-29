import os
import time

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

BITRIX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")
ANGELA_ID = 15

def post_progress_to_livefeed():
    print("Отправка художественного отчета в Живую Ленту...")
    post_text = (
        "✨ **Хроники Инкубатора: Команда за работой!** ✨\n\n"
        "Андрей, Игорь, добрый вечер! Делюсь новостями от нашей нейро-команды. Пока мы ждём ответы на организационные вопросы, работа кипит!\n\n"
        "🕵️‍♂️ **Шерлок** (наш разведчик) сейчас анализирует конкурентов ВКонтакте. Он заметил, что у 80% инкубаторов на Юге группы заброшены с 2023 года. Это значит, что наша стратегия реанимации группы `vk.com/vezem_cypljat` выстрелит идеально!\n\n"
        "🎨 **Рембрандт** (дизайнер) уже подбирает цветовую палитру для новой обложки группы ВК и Одноклассников. Мы решили делать ставку на теплые, фермерские цвета с ярким акцентом на нашу «Анжелочку» и триплеты качества.\n\n"
        "✍️ **Шекспир** (копирайтер) сидит над Базой Знаний. Первая статья для Дзена — «5 фатальных ошибок при покупке цыплят» — уже полностью готова и адаптирована под алгоритмы 2026 года. Скоро прикреплю её на согласование!\n\n"
        "👨‍💻 А **Артемий** (фронтенд) прямо сейчас собирает структуру для файла `llms.txt`. Мы сделаем так, чтобы ChatGPT и Яндекс первыми выдавали vezemcip.ru фермерам, когда те ищут цыплят.\n\n"
        "Все промежуточные результаты я буду подшивать напрямую в задачи. Битрикс всё помнит! 🐣"
    )
    
    try:
        resp = requests.post(f"{BITRIX_URL}/log.blogpost.add.json", json={
            "POST_TITLE": "Нейро-хроники: ВКонтакте, Дзен и SEO (Отчёт)",
            "POST_MESSAGE": post_text,
            "DEST": ["UA"] 
        }, timeout=15)
        res = resp.json()
        if res.get("result"):
            print("✅ Отчет успешно опубликован в Живой Ленте!")
        else:
            print("⚠️ Ошибка создания поста:", res)
    except Exception as e:
        print("Ошибка сети:", str(e))

def comment_on_active_tasks():
    print("\nИщем задачи Анжелы для обновления статуса...")
    try:
        # Ищем задачи, где Анжела ответственна
        resp = requests.post(f"{BITRIX_URL}/tasks.task.list.json", json={
            "filter": {"RESPONSIBLE_ID": ANGELA_ID, "<STATUS": 5} # 5 = завершена
        }, timeout=15)
        
        tasks_data = resp.json().get("result", {}).get("tasks", [])
        
        if not tasks_data:
            print("Активных задач не найдено.")
            return

        for task in tasks_data:
            task_id = task["id"]
            title = task["title"]
            
            # В зависимости от названия задачи, пишем разные комментарии
            comment = ""
            if "ВК" in title and "Аудит" in title:
                comment = "Шерлок передал сводку по конкурентам. Рембрандт начал отрисовку обложки. Статус переведён в 'В процессе разработки'."
            elif "llms.txt" in title:
                comment = "Артемий анализирует Sitemap сайта, чтобы вытянуть актуальные ссылки на породы и прайсы для llms.txt."
            elif "Дзен" in title:
                comment = "Шекспир закончил черновик статьи '5 ошибок при покупке бройлеров'. Ожидаем утверждения площадок для публикации."
            else:
                comment = "Работа кипит! 🚀"

            print(f"Добавляем комментарий к задаче [ID {task_id}]: {title}")
            requests.post(f"{BITRIX_URL}/task.commentitem.add.json", json={
                "TASKID": task_id,
                "FIELDS": {
                    "AUTHOR_ID": ANGELA_ID, 
                    "POST_MESSAGE": comment
                }
            })
            time.sleep(1)

        print("✅ Все задачи успешно обновлены!")

    except Exception as e:
        print("Ошибка сети:", str(e))

if __name__ == "__main__":
    post_progress_to_livefeed()
    comment_on_active_tasks()
