import json
import os
from datetime import datetime

import requests
from dotenv import load_dotenv
from rembrandt import RembrandtDesigner
from shakespeare import ShakespeareEditor


def to_bbcode(content):
    import re
    # Если на входе пришел словарь (ошибка Шекспира), превращаем его в текст
    if isinstance(content, dict):
        text = ""
        for k, v in content.items():
            if k.startswith('h2'):
                text += f"\n## {v}\n"
            elif k.startswith('content') or k == 'introduction':
                text += f"{v}\n"
            elif k == 'title':
                text += f"# {v}\n"
            else:
                text += f"{v}\n"
    else:
        text = str(content)

    # Красивое BBCode форматирование
    text = re.sub(r'# (.+)', r'[b][size=18]\1[/size][/b]\n', text)
    text = re.sub(r'## (.+)', r'\n[b][size=16][color=#003366]— \1[/color][/size][/b]\n', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'[b]\1[/b]', text)
    text = re.sub(r'• (.+)', r'  [color=#555555]●[/color] \1', text)
    
    return text

def run_full_beauty_cycle(topic="5 главных ошибок начинающего птицевода при покупке суточных цыплят"):
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
    webhook_url = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL").rstrip('/')
    
    print(f"🚀 Запуск КОНТЕНТ-МАШИНЫ 2.0 (Исправление формата) для темы: {topic}")
    
    # 1. ШЕКСПИР
    shakespeare = ShakespeareEditor()
    brief = {
        "topic": topic,
        "seo_keywords": ["суточные цыплята", "бройлеры", "Азов", "инкубатор", "КОББ-500", "РОСС-308"],
        "requirements": "Максимальный E-E-A-T стиль. Только текст в ответах JSON, без вложенности."
    }
    content = shakespeare.write_article(brief)
    
    # 2. РЕМБРАНДТ (Сочная картинка с запасом)
    rembrandt = RembrandtDesigner()
    # Используем качественный источник, пока не настроим локальную загрузку
    image_url = "https://images.unsplash.com/photo-1548550023-2bdb3c5beed7?auto=format&fit=crop&q=80&w=800"
    
    # 3. СОХРАНЯЕМ ЧЕРНОВИК ДЛЯ АНЖЕЛЫ (чтобы она могла его выложить на диск при одобрении)
    draft_data = {
        "topic": topic,
        "content": content,
        "folder_name": f"{datetime.now().strftime('%Y-%m-%d')}_Chicks_Mistakes"
    }
    draft_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'content_drafts', 'last_draft.json')
    os.makedirs(os.path.dirname(draft_path), exist_ok=True)
    with open(draft_path, 'w', encoding='utf-8') as f:
        json.dump(draft_data, f, ensure_ascii=False, indent=2)

    # 4. ПОСТ В ЛЕНТУ
    beauty_text = to_bbcode(content.get('zen', content.get('vk', 'Текст готов')))
    
    # 📝 КРАТКАЯ СВОДКА ДЛЯ ЖИВОЙ ЛЕНТЫ (только статус обновления)
    post_message = (
        f"🐣 **АНЖЕЛА ПТЕНЧИКОВА: Черновик статьи готов!**\n\n"
        f"Тема: «{topic}»\n"
        f"Все черновики (VK, DZEN, OK) сгенерированы Шекспиром и отправлены Игорю в личные сообщения в Telegram.\n"
        f"Ждем подтверждения, чтобы выложить на Диск!"
    )
    
    requests.post(f"{webhook_url}/log.blogpost.add.json", json={
        "POST_TITLE": f"🏆 ОТЧЕТ: Задача {topic} выполнена",
        "POST_MESSAGE": post_message,
        "DEST": ["UA"]
    })
    
    # 📱 ПОЛНЫЙ ОТЧЕТ В ТЕЛЕГРАМ С ИНЛАЙН КНОПКАМИ
    tg_token = os.getenv("ANGELOCHKA_BOT_TOKEN")
    owner_id = 176203333  # Игорь
    proxy_url = os.getenv("TELEGRAM_PROXY")
    
    proxies = {}
    if proxy_url:
        p = proxy_url.replace("socks5://", "socks5h://")
        proxies = {"https": p, "http": p}
        
    if tg_token:
        # Отправляем Картинку с подписью
        caption = f"🐣 **АНЖЕЛА ПТЕНЧИКОВА: Черновик готов!**\n\nТема: <b>{topic}</b>\n(Полный текст ниже)\n\nШеф, куда деваем?"
        keyboard = {
            "inline_keyboard": [
                [{"text": "✅ ОК (Одобрить и на Диск)", "callback_data": "approve_draft"}],
                [{"text": "📝 Переделать", "callback_data": "reject_draft"}]
            ]
        }
        
        # Сначала отправляем картинку с кнопками
        requests.post(
            f"https://api.telegram.org/bot{tg_token}/sendPhoto",
            json={
                "chat_id": owner_id, 
                "photo": image_url, 
                "caption": caption, 
                "parse_mode": "HTML",
                "reply_markup": keyboard
            },
            proxies=proxies,
            timeout=15
        )
        # Потом отправляем сам длинный текст
        text_for_tg = beauty_text.replace('[b]', '<b>').replace('[/b]', '</b>')
        text_for_tg = text_for_tg.replace('[size=18]', '').replace('[/size]', '')
        text_for_tg = text_for_tg.replace('[size=16]', '').replace('[color=#003366]', '').replace('[/color]', '')
        text_for_tg = text_for_tg.replace('[color=#555555]', '')
        if len(text_for_tg) > 4000:
            text_for_tg = text_for_tg[:3997] + "..."
            
        requests.post(
            f"https://api.telegram.org/bot{tg_token}/sendMessage",
            json={"chat_id": owner_id, "text": text_for_tg, "parse_mode": "HTML"},
            proxies=proxies,
            timeout=15
        )
    
    print("🎉 ВСЁ ОК! Текст причесан, папки созданы.")

if __name__ == "__main__":
    run_full_beauty_cycle()
