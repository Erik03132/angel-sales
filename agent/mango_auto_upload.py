#!/usr/bin/env python3
"""
Mango Office — автоматическая загрузка MP3 через Selenium

Скрипт автоматически:
1. Логинится в ЛК Mango Office
2. Загружает MP3 файл через веб-интерфейс
3. Настраивает Webhook URL
4. Возвращает имя файла в системе

Использование:
    python3 mango_auto_upload.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Загрузка секретов из .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Конфигурация
MANGO_LOGIN = os.getenv("MANGO_LOGIN", "")
MANGO_PASSWORD = os.getenv("MANGO_PASSWORD", "")
MANGO_LK_URL = 'https://office.mango-office.ru'

MP3_FILE = '/Users/igorvasin/freelance-2026/ai-eggs/agent/andrej_call_100_gosyat.mp3'
WEBHOOK_URL = 'https://webhook.site/unique-id'  # Заменить на свой


def setup_driver():
    """Настройка Chrome WebDriver"""
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    
    driver = webdriver.Chrome(service=Service(), options=chrome_options)
    return driver


def login(driver):
    """Логин в ЛК Mango"""
    print("🔐 Логин в ЛК Mango...")
    
    driver.get(MANGO_LK_URL)
    
    # Ждем форму логина
    wait = WebDriverWait(driver, 30)
    
    # Ищем поле логина
    try:
        login_input = wait.until(EC.presence_of_element_located((By.NAME, 'login')))
        login_input.send_keys(MANGO_LOGIN)
        
        password_input = driver.find_element(By.NAME, 'password')
        password_input.send_keys(MANGO_PASSWORD)
        
        # Кнопка входа
        submit_btn = driver.find_element(By.XPATH, '//button[@type="submit"]')
        submit_btn.click()
        
        print("   ✅ Успешный вход")
        time.sleep(3)
        
        return True
        
    except Exception as e:
        print(f"   ❌ Ошибка логина: {e}")
        return False


def upload_mp3(driver):
    """Загрузка MP3 файла"""
    print("\n📤 Загрузка MP3 файла...")
    
    try:
        # Переход в раздел Виртуальная АТС
        vpbx_link = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.LINK_TEXT, 'Виртуальная АТС'))
        )
        vpbx_link.click()
        time.sleep(2)
        
        # Переход в раздел Файлы
        files_link = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.LINK_TEXT, 'Файлы'))
        )
        files_link.click()
        time.sleep(2)
        
        # Кнопка загрузки
        upload_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CLASS_NAME, 'upload-btn'))
        )
        upload_btn.click()
        time.sleep(1)
        
        # Загрузка файла через input
        file_input = driver.find_element(By.XPATH, '//input[@type="file"]')
        file_input.send_keys(MP3_FILE)
        
        print(f"   📁 Файл: {os.path.basename(MP3_FILE)}")
        
        # Ожидаем завершения загрузки
        time.sleep(5)
        
        # Получаем имя файла в системе
        filename_element = driver.find_element(By.CLASS_NAME, 'file-name')
        filename = filename_element.text
        
        print(f"   ✅ Файл загружен: {filename}")
        
        return filename
        
    except Exception as e:
        print(f"   ❌ Ошибка загрузки: {e}")
        return None


def configure_webhook(driver, webhook_url):
    """Настройка Webhook URL"""
    print(f"\n🔔 Настройка Webhook: {webhook_url}")
    
    try:
        # Переход в Интеграции
        integrations_link = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.LINK_TEXT, 'Интеграции'))
        )
        integrations_link.click()
        time.sleep(2)
        
        # API коннектор
        api_link = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.LINK_TEXT, 'API коннектор'))
        )
        api_link.click()
        time.sleep(2)
        
        # Поле URL
        url_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, 'webhook_url'))
        )
        url_input.clear()
        url_input.send_keys(webhook_url)
        
        # Сохранить
        save_btn = driver.find_element(By.XPATH, '//button[text()="Сохранить"]')
        save_btn.click()
        
        print("   ✅ Webhook настроен")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Ошибка настройки webhook: {e}")
        return False


def main():
    print("=== Mango Office — Автоматическая загрузка MP3 ===\n")
    
    # Проверка файла
    if not os.path.exists(MP3_FILE):
        print(f"❌ MP3 файл не найден: {MP3_FILE}")
        return
    
    # Настройка драйвера
    driver = setup_driver()
    
    try:
        # Логин
        if not login(driver):
            print("\n❌ Не удалось войти в ЛК Mango")
            return
        
        # Загрузка MP3
        filename = upload_mp3(driver)
        
        if filename:
            print(f"\n✅ MP3 загружен: {filename}")
            
            # Настройка webhook
            # configure_webhook(driver, WEBHOOK_URL)
            
            print("\n=== Готово ===")
            print("\n📞 Для звонка выполни:")
            print("   python3 ai-eggs/agent/mango_auto_call_full.py ai-eggs/data/mango/clients.csv --delay 30")
            print("\n⚙️  Параметры:")
            print(f"   MP3 файл: {filename}")
            print(f"   Webhook: {WEBHOOK_URL}")
        else:
            print("\n❌ Не удалось загрузить MP3")
    
    finally:
        driver.quit()


if __name__ == '__main__':
    main()
