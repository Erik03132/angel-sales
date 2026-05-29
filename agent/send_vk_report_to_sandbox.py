#!/usr/bin/env python3
"""
Загружает VK-отчёт на Битрикс Диск (песочница) и отправляет уведомление Андрею.
"""
import base64
import os
import sys

import requests

SANDBOX_URL = "https://b24-mjxvhq.bitrix24.ru/rest/1/3crdltc04zo7fp8l"
ANDREY_ID = 16  # Иван Иванов = Андрей в песочнице
STORAGE_ID = 3   # Общий диск

def upload_to_disk(file_path, file_name):
    """Загрузка файла на Общий диск Битрикс24."""
    with open(file_path, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")
    
    # Сначала найдём или создадим папку VK_Reports
    resp = requests.get(f"{SANDBOX_URL}/disk.storage.getchildren.json", params={"id": STORAGE_ID})
    folder_id = None
    for item in resp.json().get("result", []):
        if item.get("NAME") == "VK_Reports" and item.get("TYPE") == "folder":
            folder_id = item["ID"]
            break
    
    if not folder_id:
        resp = requests.post(f"{SANDBOX_URL}/disk.storage.addfolder.json", json={
            "id": STORAGE_ID,
            "data": {"NAME": "VK_Reports"}
        })
        folder_id = resp.json().get("result", {}).get("ID")
        print(f"  📂 Создана папка VK_Reports (ID: {folder_id})")
    
    # Загружаем файл
    resp = requests.post(f"{SANDBOX_URL}/disk.folder.uploadfile.json", json={
        "id": folder_id,
        "data": {"NAME": file_name},
        "fileContent": content
    })
    result = resp.json().get("result", {})
    file_id = result.get("ID")
    download_url = result.get("DOWNLOAD_URL", "")
    print(f"  ✅ Файл загружен! ID: {file_id}")
    return file_id, download_url


def send_message(text, dialog_id=ANDREY_ID):
    """Отправка сообщения в песочницу."""
    resp = requests.post(f"{SANDBOX_URL}/im.message.add.json", json={
        "DIALOG_ID": dialog_id,
        "MESSAGE": text[:4000]
    }, timeout=15)
    if resp.status_code == 200 and resp.json().get("result"):
        msg_id = resp.json()["result"]
        print(f"  ✅ Сообщение отправлено (msg #{msg_id})")
        return msg_id
    else:
        print(f"  ⚠️ Ошибка: {resp.status_code} — {resp.text[:300]}")
        return None


def main():
    html_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VK_REPORT_ANDREY.html")
    
    if not os.path.exists(html_path):
        print(f"❌ Файл не найден: {html_path}")
        sys.exit(1)
    
    print("📤 Загружаю отчёт на Битрикс Диск...")
    file_id, download_url = upload_to_disk(html_path, "VK_Экспансия_Отчёт_29апреля.html")
    
    print("💬 Отправляю уведомление Андрею...")
    
    message = """[B]📊 ОТЧЁТ: VK Экспансия — ВеземЦыплят[/B]

Андрей, готов полный отчёт по выходу в ВКонтакте!

[B]Что внутри:[/B]
• ТОП-7 сообществ ВК по птицеводству (от 400К подписчиков)
• Какие форматы контента дают ×5–10 охват
• Стратегия экспансии в 3 фазы
• VK Mini App — заказ прямо в ВК (мы первые в нише!)
• Контент-план: 28 постов/мес + VK Clips
• KPI и таймлайн

[B]🔥 Главный инсайт:[/B] VK Mini Apps в птицеводстве = ПУСТАЯ НИША. Ни у кого нет!

📎 Отчёт загружен на Общий Диск → папка [B]VK_Reports[/B]
Скачай HTML-файл и открой в браузере — там красивые таблицы и графика.

[I]Подготовлено: Antigravity AI / 29.04.2026[/I]"""

    send_message(message)
    
    print("\n🎉 Готово! Отчёт на диске + уведомление отправлено.")


if __name__ == "__main__":
    main()
