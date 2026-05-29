#!/usr/bin/env python3
"""
📢 OK Selenium Autoposter — публикация в Одноклассники через браузер.

Почему Selenium, а не API:
  OK закрыл создание External-приложений в 2023 году.
  VK Mini Apps не поддерживают OAuth для сервера.
  Selenium — реальный путь, который используют SMMplanner и другие.

Нужные переменные в .env:
  OK_LOGIN   — email или телефон (incubird@yandex.ru)
  OK_PASS    — пароль
  OK_PODVORYE_GROUP_ID — 70000050244449

Зависимости:
  pip install selenium webdriver-manager pillow

Использование:
  python3 ok_selenium_poster.py podvorye           # 1 пост
  python3 ok_selenium_poster.py podvorye --count 3 # 3 поста
  python3 ok_selenium_poster.py podvorye --dry-run # просмотр без публикации
  python3 ok_selenium_poster.py podvorye --list    # список неопубликованных
  python3 ok_selenium_poster.py podvorye --headless # без GUI (для сервера)
"""

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_DIR = os.path.join(BASE_DIR, "agent")
sys.path.insert(0, AGENT_DIR)

from vk_smart_poster import _make_imagen_prompt, generate_imagen_photo, parse_all_posts

# ═══════════════════════════════════════════════
# Конфигурация
# ═══════════════════════════════════════════════

CONTENT_DIR = os.path.join(BASE_DIR, "vk_content")

GROUPS = {
    "podvorye": {
        "env_group_id": "OK_PODVORYE_GROUP_ID",
        "name": "Своё Подворье (OK)",
        "content_dir": os.path.join(CONTENT_DIR, "podvorye"),
        "posted_log": os.path.join(CONTENT_DIR, "podvorye", "ok_posted_log.json"),
        "default_photo_prompt": (
            "Charming Russian rural farmstead with wooden house, vegetable garden, "
            "free-range chickens on green grass, warm golden hour light. "
            "No text, no words, no letters, no watermarks."
        ),
    },
}

OK_GROUP_URL = "https://ok.ru/group/{group_id}"


# ═══════════════════════════════════════════════
# Вспомогательные функции
# ═══════════════════════════════════════════════

def load_env() -> dict:
    env = {}
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    for k, v in os.environ.items():
        if k not in env:
            env[k] = v
    return env


def load_posted(path: str) -> dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_posted(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_next_posts(content_dir: str, posted_log_path: str, count: int = 1) -> list:
    all_posts = parse_all_posts(content_dir)
    posted = load_posted(posted_log_path)
    posted_keys = set(posted.get("_keys", []))
    posted_indices = set(str(k) for k in posted.keys() if k != "_keys")

    unpublished = []
    for post in all_posts:
        key = post.get("post_id_key", "")
        idx = str(post.get("index", 0))
        if key not in posted_keys and idx not in posted_indices:
            unpublished.append(post)

    return unpublished[:count]


# ═══════════════════════════════════════════════
# Selenium OK Poster
# ═══════════════════════════════════════════════

class OKSeleniumPoster:
    """Публикует посты в OK-группу через браузерную автоматизацию."""

    LOGIN_URL = "https://ok.ru/dk?cmd=AnonymPage&st.cmd=anonymLogin"

    def __init__(self, login: str, password: str, group_id: str, headless: bool = False):
        self.login = login
        self.password = password
        self.group_id = group_id
        self.headless = headless
        self.driver = None

    def _get_driver(self):
        """Инициализирует Chrome через webdriver-manager."""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
        except ImportError:
            print("  ❌ Установите зависимости: pip install selenium webdriver-manager")
            return None

        opts = Options()
        if self.headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1280,900")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)

        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=opts)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e:
            print(f"  ❌ Chrome не запустился: {e}")
            print("  💡 Установите Chrome: brew install --cask google-chrome")
            return None

    def login_ok(self) -> bool:
        """Авторизуется на ok.ru."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        print(f"  🔐 Авторизация на ok.ru ({self.login[:5]}...)...")
        self.driver.get(self.LOGIN_URL)
        time.sleep(2)

        try:
            wait = WebDriverWait(self.driver, 15)

            # Поле логина
            login_field = wait.until(EC.presence_of_element_located((By.NAME, "st.email")))
            login_field.clear()
            login_field.send_keys(self.login)

            # Поле пароля
            pass_field = self.driver.find_element(By.NAME, "st.password")
            pass_field.clear()
            pass_field.send_keys(self.password)

            # Кнопка входа
            submit = self.driver.find_element(By.XPATH, "//input[@type='submit'] | //button[@type='submit']")
            submit.click()
            time.sleep(3)

            # Проверяем успешность входа
            if "ok.ru" in self.driver.current_url and "AnonymPage" not in self.driver.current_url:
                print("  ✅ Авторизация успешна")
                return True
            else:
                print(f"  ❌ Ошибка авторизации. URL: {self.driver.current_url[:80]}")
                return False

        except Exception as e:
            print(f"  ❌ Ошибка при входе: {e}")
            return False

    def post(self, text: str, photo_path: str = None) -> str | None:
        """
        Публикует пост в группу OK.
        Возвращает URL опубликованного поста или None.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        group_url = OK_GROUP_URL.format(group_id=self.group_id)
        print(f"  🌐 Открываем группу: {group_url}")
        self.driver.get(group_url)
        time.sleep(3)

        try:
            wait = WebDriverWait(self.driver, 20)

            # Ищем поле "Написать что-нибудь" / кнопку создания поста
            post_trigger = None
            selectors = [
                "//div[contains(@class, 'create-post')]",
                "//div[@data-l='t,createPostLink']",
                "//span[contains(text(), 'Написать')]",
                "//div[contains(@class, 'posting-input')]",
                "//textarea[contains(@placeholder, 'Напишите')]",
                "//div[@class='stub_txt' and contains(text(), 'Написать')]",
            ]

            for sel in selectors:
                try:
                    el = self.driver.find_element(By.XPATH, sel)
                    if el.is_displayed():
                        post_trigger = el
                        break
                except Exception:
                    continue

            if not post_trigger:
                print("  ❌ Не нашли поле создания поста")
                print(f"  📋 Страница: {self.driver.title}")
                return None

            post_trigger.click()
            time.sleep(2)

            # Если есть фото — загружаем сначала
            if photo_path and os.path.exists(photo_path):
                try:
                    file_input = self.driver.find_element(
                        By.XPATH, "//input[@type='file']"
                    )
                    file_input.send_keys(photo_path)
                    print("  📸 Фото загружается...")
                    time.sleep(5)  # Ждём загрузки фото
                except Exception as e:
                    print(f"  ⚠️ Фото не загрузилось: {e}")

            # Находим текстовое поле и вводим текст
            text_area = None
            text_selectors = [
                "//div[@contenteditable='true']",
                "//textarea[contains(@class, 'posting')]",
                "//div[@role='textbox']",
            ]
            for sel in text_selectors:
                try:
                    el = wait.until(EC.presence_of_element_located((By.XPATH, sel)))
                    if el.is_displayed():
                        text_area = el
                        break
                except Exception:
                    continue

            if not text_area:
                print("  ❌ Не нашли текстовое поле")
                return None

            text_area.click()
            time.sleep(0.5)

            # Вводим текст по частям (OK ограничивает скорость ввода)
            for chunk in [text[i:i+100] for i in range(0, len(text), 100)]:
                text_area.send_keys(chunk)
                time.sleep(0.2)

            time.sleep(1)

            # Кнопка публикации
            submit_selectors = [
                "//button[contains(@class, 'posting-submit')]",
                "//button[contains(text(), 'Поделиться')]",
                "//button[contains(text(), 'Опубликовать')]",
                "//input[@value='Поделиться']",
                "//div[@data-l='t,submit']",
            ]

            submit_btn = None
            for sel in submit_selectors:
                try:
                    el = self.driver.find_element(By.XPATH, sel)
                    if el.is_displayed() and el.is_enabled():
                        submit_btn = el
                        break
                except Exception:
                    continue

            if not submit_btn:
                print("  ❌ Не нашли кнопку публикации")
                return None

            submit_btn.click()
            print("  ⏳ Публикуем...")
            time.sleep(5)

            # Пробуем получить URL последнего поста
            current_url = self.driver.current_url
            print(f"  ✅ Опубликовано! URL группы: {current_url}")
            return current_url

        except Exception as e:
            print(f"  ❌ Ошибка публикации: {e}")
            return None

    def close(self):
        if self.driver:
            self.driver.quit()

    def __enter__(self):
        self.driver = self._get_driver()
        return self

    def __exit__(self, *args):
        self.close()


# ═══════════════════════════════════════════════
# TG уведомление
# ═══════════════════════════════════════════════

def send_tg_report(results_all: dict, env: dict) -> None:
    import subprocess
    import urllib.parse
    tg_token = env.get("ANGELOCHKA_BOT_TOKEN", "")
    chat_id = env.get("OWNER_CHAT_ID", "176203333")
    if not tg_token:
        return

    total = sum(len(r) for r in results_all.values())
    ok_count = sum(1 for rs in results_all.values() for r in rs if r.get("status") == "ok")

    lines = [f"📢 *OK Autoposter* — {datetime.now().strftime('%d.%m.%Y %H:%M')}", ""]
    for group, results in results_all.items():
        name = GROUPS[group]["name"]
        for r in results:
            if r.get("status") == "ok":
                url = r.get("url", "")
                lines.append(f"✅ {name}: [группа]({url})" if url else f"✅ {name}: опубликован")
            elif r.get("status") == "dry-run":
                lines.append(f"🔸 {name}: dry-run")
            else:
                lines.append(f"❌ {name}: ошибка")

    lines.append(f"\nИтого: {ok_count}/{total}")
    text = "\n".join(lines)

    try:
        proxy = env.get("TELEGRAM_PROXY", "")
        cmd = ["curl", "-s", "--max-time", "10"]
        if proxy:
            cmd.extend(["--proxy", proxy])
        cmd.extend([
            "-X", "POST",
            f"https://api.telegram.org/bot{tg_token}/sendMessage",
            "-d", f"chat_id={chat_id}&text={urllib.parse.quote(text)}&parse_mode=Markdown&disable_web_page_preview=true",
        ])
        subprocess.run(cmd, timeout=15, capture_output=True)
    except Exception as e:
        print(f"  ⚠️ TG: {e}")


# ═══════════════════════════════════════════════
# Логика публикации
# ═══════════════════════════════════════════════

def publish_group(group_key: str, env: dict, count: int = 1,
                  dry_run: bool = False, headless: bool = False) -> list:
    cfg = GROUPS[group_key]
    group_id = env.get(cfg["env_group_id"], "").lstrip("-")
    ok_login = env.get("OK_LOGIN", "")
    ok_pass = env.get("OK_PASS", "")

    if not group_id:
        print(f"❌ {cfg['name']}: {cfg['env_group_id']} не найден в .env")
        return []

    if not dry_run and (not ok_login or not ok_pass):
        print("❌ OK_LOGIN / OK_PASS не заданы в .env")
        return []

    posts = get_next_posts(cfg["content_dir"], cfg["posted_log"], count)
    if not posts:
        print(f"✅ {cfg['name']}: все посты опубликованы!")
        return []

    print(f"\n{'═' * 50}")
    print(f"  📢 {cfg['name']} — {len(posts)} пост(ов) к публикации")
    print(f"{'═' * 50}")

    if dry_run:
        for i, p in enumerate(posts, 1):
            print(f"  [{i}] DRY-RUN: {p['text'][:70]}...")
        return [{"status": "dry-run"} for _ in posts]

    results = []
    posted_log = load_posted(cfg["posted_log"])
    posted_keys = set(posted_log.get("_keys", []))

    with OKSeleniumPoster(ok_login, ok_pass, group_id, headless=headless) as poster:
        if not poster.driver:
            return []

        if not poster.login_ok():
            return []

        for i, post in enumerate(posts):
            print(f"\n  [{i + 1}/{len(posts)}] {post['text'][:60]}...")

            # Генерация фото
            photo_tmp = None
            prompt = _make_imagen_prompt(post["text"], post.get("meta", {}), cfg["default_photo_prompt"])
            print(f"  🎨 Imagen 4.0: «{prompt[:60]}»...")
            photo_bytes = generate_imagen_photo(prompt, env)
            if photo_bytes:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    f.write(photo_bytes)
                    photo_tmp = f.name
                print(f"  📸 Фото: {len(photo_bytes)//1024} KB")

            # Публикация
            url = poster.post(post["text"], photo_path=photo_tmp)

            # Удаляем временный файл фото
            if photo_tmp:
                try:
                    os.unlink(photo_tmp)
                except Exception:
                    pass

            if url:
                key = post.get("post_id_key", str(post.get("index", i)))
                posted_keys.add(key)
                posted_log[str(post.get("index", i + 1))] = {
                    "url": url,
                    "posted_at": datetime.now().isoformat(),
                    "source_file": post.get("source_file", "?"),
                    "text_preview": post["text"][:80],
                    "has_photo": bool(photo_bytes),
                    "method": "selenium",
                }
                posted_log["_keys"] = list(posted_keys)
                save_posted(cfg["posted_log"], posted_log)
                results.append({"status": "ok", "url": url})
            else:
                results.append({"status": "fail"})

            if i < len(posts) - 1:
                print("  ⏳ Пауза 10 сек...")
                time.sleep(10)

    return results


# ═══════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="OK Selenium Autoposter")
    parser.add_argument("group", choices=list(GROUPS.keys()), help="Группа для постинга")
    parser.add_argument("--count", "-n", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--headless", action="store_true", help="Без GUI (для VPS)")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    env = load_env()
    groups = [args.group]

    if args.list:
        for g in groups:
            cfg = GROUPS[g]
            posts = get_next_posts(cfg["content_dir"], cfg["posted_log"], count=100)
            print(f"\n{'═' * 50}")
            print(f"  {cfg['name']}: {len(posts)} неопубликованных")
            print(f"{'═' * 50}")
            for idx, p in enumerate(posts[:10], 1):
                print(f"  {idx}. [{p.get('source_file', '?')}] {p['text'][:70]}...")
        return

    results_all = {}
    for g in groups:
        results = publish_group(g, env, count=args.count,
                                dry_run=args.dry_run, headless=args.headless)
        results_all[g] = results

    if not args.dry_run:
        send_tg_report(results_all, env)

    total = sum(len(r) for r in results_all.values())
    ok_count = sum(1 for rs in results_all.values() for r in rs if r.get("status") == "ok")
    print(f"\n{'═' * 50}")
    print(f"  📊 ИТОГО: {ok_count}/{total} опубликовано")
    print(f"{'═' * 50}")


if __name__ == "__main__":
    main()
