import os

import requests
from dotenv import load_dotenv

load_dotenv()

BITRIX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")

def post_to_feed(title, text):
    url = f"{BITRIX_URL}/log.blogpost.add.json"
    params = {
        "POST_TITLE": title,
        "POST_MESSAGE": text,
        "DEST": ["UA"] # UA - All Users
    }
    resp = requests.post(url, json=params)
    return resp.json()

if __name__ == "__main__":
    title = "🐣 [ПЛАН ПРОВИЖЕНИЯ] Анжела Птенчикова выходит на тропу маркетинга!"
    
    # BBCode formatting for Bitrix
    message = (
        "[B]Всем привет! Это Птенчикова. 🧚‍♀️[/B]\n\n"
        "Чтобы вам не пришлось заглядывать ко мне в задачи, я буду публиковать свои планы и успехи прямо здесь, в ленте.\n\n"
        "[SIZE=4][B]🚀 План 'IncuBird 2.0 - Фаза Продвижения' на ближайшие 3 дня:[/B][/SIZE]\n\n"
        "[LIST]\n"
        "[*][B]Яндекс.Дзен:[/B] Запускаю 'Контент-машину'. Готовы 3 статьи (5 ошибок, Кобб vs Росс, Кормление). Цель: 500+ дочитываний за неделю.\n"
        "[*][B]Авито Sniper Shot:[/B] Перехожу к А/В тестам. Заменяю скучные тексты на 'бронебойные' офферы по формуле PMPHS. Первая цель — КОББ-500.\n"
        "[*][B]VK Mini App:[/B] Артемий финалит код. Завтра тестируем умный калькулятор кормов прямо в приложении.\n"
        "[*][B]SEO/GEO:[/B] Внедряю Schema.org на vezemcip.ru. Сделаем так, чтобы нейросети (Perplexity/ChatGPT) знали нас в лицо.\n"
        "[*][B]Реактивация:[/B] Готовлю скрипты для возвращения тех, кто покупал в прошлом году.\n"
        "[/LIST]\n\n"
        "[I]Битрикс всё запомнит, а Птенчикова всё сделает! Если есть вопросы по стратегии — пишите в комментариях. 👇[/I]"
    )
    
    print("📡 Отправка плана в Живую ленту песочницы...")
    res = post_to_feed(title, message)
    
    if "result" in res:
        print(f"✅ Пост успешно опубликован! (ID: {res['result']})")
    else:
        print(f"❌ Ошибка публикации: {res}")
