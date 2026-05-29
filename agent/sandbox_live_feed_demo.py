import os
import time

import requests
from dotenv import load_dotenv
from marketer import MarketerStrategist
from rembrandt import RembrandtDesigner
from shakespeare import ShakespeareEditor

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

# Этот URL вы уже использовали для Птенчиковой в Песочнице
BITRIX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")

def to_bbcode(text):
    import re
    # Конвертация Markdown в BBCode
    text = re.sub(r'\*\*(.+?)\*\*', r'[b]\1[/b]', text)
    # Конвертация базовых HTML-тегов в BBCode
    text = re.sub(r'<h[1-6]>(.+?)</h[1-6]>', r'[b]\1[/b]\n', text)
    text = re.sub(r'<strong>(.+?)</strong>', r'[b]\1[/b]', text)
    text = re.sub(r'<p>(.*?)</p>', r'\1\n\n', text)
    # Удаление любых остальных HTML-тегов
    text = re.sub(r'<[^>]+>', '', text)
    return text

def post_to_feed(title, message):
    if not BITRIX_URL:
        print(f"[{title}] {message}")
        print("\nВНИМАНИЕ: Нет SANDBOX_BITRIX_WEBHOOK_URL, вывожу только в консоль.")
        return
    try:
        resp = requests.post(f"{BITRIX_URL}/log.blogpost.add.json", json={
            "POST_TITLE": title,
            "POST_MESSAGE": to_bbcode(message),
            "DEST": ["UA"] # Всем авторизованным пользователям (Живая лента)
        }, timeout=15)
        print(f"✅ Отправлено в Живую Ленту: {title}")
    except Exception as e:
        print("❌ Ошибка сети Битрикс:", str(e))

def run_live_demo(topic="5 главных ошибок при покупке суточных бройлеров"):
    print("Начинаю трансляцию в Живую Ленту...")
    
    # Старт
    post_to_feed(
        "🚀 ПТЕНЧИКОВА: Запускаю конвейер контента", 
        f"Андрей, Игорь, принял задачу на статью: **{topic}**.\n\n"
        "Передаю в работу нашему цифровому отделу. Буду транслировать этапы прямо сюда в Живую Ленту."
    )
    time.sleep(5)
    
    # 1. Маркетолог
    marketer = MarketerStrategist()
    brief = marketer.generate_brief(topic)
    post_to_feed(
        "📈 МАРКЕТОЛОГ: Семантика собрана", 
        f"**Отчет стратега:**\nЯ проанализировал поисковую выдачу и ответы нейросетей.\n\n"
        f"**Собраны ключи:** {', '.join(brief['seo_keywords'])}\n"
        f"**GEO Триплеты:** {brief['geo_triplets'][0]}\n"
        f"**ТЗ к тексту:** {brief['requirements']}\n\n"
        "Бриф утвержден и передан Шекспиру и Рембрандту."
    )
    time.sleep(5)
    
    # 2. Рембрандт
    rembrandt = RembrandtDesigner()
    img_url = rembrandt.generate_cover(topic, context="Испуганный фермер и больные цыплята, реализм.")
    post_to_feed(
        "🎨 РЕМБРАНДТ: Визуал готов", 
        f"Для привлечения внимания сделал эмоциональную обложку.\n\n![Обложка]({img_url})"
    )
    time.sleep(5)
    
    # 3. Шекспир
    shakespeare = ShakespeareEditor()
    article = shakespeare.write_article(brief)
    
    preview_text = (
        f"**ДЗЕН (Лонгрид):**\n{article['zen'][:150]}...\n\n"
        f"**TELEGRAM:**\n{article['telegram'][:150]}...\n\n"
        f"**ВКОНТАКТЕ:**\n{article['vk'][:150]}..."
    )
    
    post_to_feed(
        "✍️ ШЕКСПИР: Омниканальный контент готов", 
        f"Текст вычитан и адаптирован под разные площадки!\n\n---\n\n{preview_text}\n\n---\n*(MAX и Отраслевые форматы также сохранены на сервере)*"
    )
    time.sleep(5)
    
    # Финал Птенчиковой
    post_to_feed(
        f"✅ ПТЕНЧИКОВА: Релиз-кандидат '{topic}'", 
        f"Коллеги, процесс завершен!\n\n"
        f"![Изображение]({img_url})\n\n"
        f"Все 5 форматов текстов готовы (TG, VK, Zen, MAX, Industry).\n\n"
        "**Жду вашего согласования для автоматической рассылки по каналам!**"
    )
    print("Трансляция завершена.")

if __name__ == "__main__":
    run_live_demo()
