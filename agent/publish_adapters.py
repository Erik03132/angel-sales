#!/usr/bin/env python3
"""
publish_adapters.py — адаптеры для мульти‑публикации постов.
Содержит dataclass Post и функции publish_to_tg, publish_to_ok, publish_to_dzen.
Токены/ключи берутся из .env (через os.getenv).
"""

import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import requests


# ---------------------------------------------------------------------------
# Модель поста (единственный источник правды для всех адаптеров)
# ---------------------------------------------------------------------------
@dataclass
class Post:
    title: str
    text: str               # основной текст публикации (без заголовка)
    image_path: Optional[Path] = None
    tags: List[str] = None
    datetime: str = None    # ISO‑строка, например "2026-05-12T10:00:00"
    ready: bool = True      # флаг, что пост готов к публикации

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

# ---------------------------------------------------------------------------
# Telegram — внутренний хелпер
# ---------------------------------------------------------------------------
BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHANNEL_ID = os.getenv("TG_CHANNEL_ID")              # основной канал "@my_channel"
DZEN_BRIDGE_CHANNEL_ID = os.getenv("DZEN_BRIDGE_CHANNEL_ID")  # ТГ‑канал‑мост для Дзена

def _send_tg(post: Post, channel_id: str, label: str = "Telegram") -> bool:
    """Низкоуровневая отправка поста в указанный Telegram‑канал.
    Возвращает True при успехе.
    """
    if not BOT_TOKEN or not channel_id:
        logging.warning(f"{label}: credentials/channel not set – skipping.")
        return False

    base_url = f"https://api.telegram.org/bot{BOT_TOKEN}"

    # ── формируем текст ──
    caption = f"<b>{post.title}</b>\n\n{post.text}"
    if post.tags:
        caption += "\n\n" + " ".join(f"#{t}" for t in post.tags)

    try:
        if post.image_path and Path(post.image_path).exists():
            # sendPhoto: caption ≤ 1024 символа
            truncated = caption[:1024]
            with open(post.image_path, "rb") as img:
                resp = requests.post(
                    f"{base_url}/sendPhoto",
                    data={"chat_id": channel_id, "caption": truncated, "parse_mode": "HTML"},
                    files={"photo": img},
                    timeout=30,
                )
        else:
            resp = requests.post(
                f"{base_url}/sendMessage",
                data={
                    "chat_id": channel_id,
                    "text": caption,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                },
                timeout=15,
            )
        resp.raise_for_status()
        logging.info(f"✅ {label}: пост опубликован.")
        return True
    except Exception as e:
        logging.error(f"❌ {label}: ошибка публикации – {e}")
        return False

# ---------------------------------------------------------------------------
# Telegram adapter (основной канал)
# ---------------------------------------------------------------------------
def publish_to_tg(post: Post) -> bool:
    """Публикует пост в основной Telegram‑канал (TG_CHANNEL_ID)."""
    return _send_tg(post, TG_CHANNEL_ID, label="TG‑канал")

# ---------------------------------------------------------------------------
# Yandex.Dzen adapter (через TG‑канал‑мост)
# ---------------------------------------------------------------------------
#
# Схема:  Python  →  TG‑канал‑мост  →  Дзен (автоимпорт из привязанного TG)
#
# Настройка на стороне Дзена:
#   1. Создать отдельный публичный Telegram‑канал (например, @podvorye_dzen).
#   2. Добавить бота (TG_BOT_TOKEN) администратором этого канала.
#   3. В «Дзен Студии» → «Импорт» → привязать этот ТГ‑канал.
#   4. Прописать в .env:  DZEN_BRIDGE_CHANNEL_ID=@podvorye_dzen
#
# После этого каждый publish_to_dzen() автоматически публикует в ТГ‑мост,
# а Дзен сам подтягивает контент.
# ---------------------------------------------------------------------------
def _compact_text(text: str) -> str:
    """Убирает двойные пустые строки — Дзен делает из них огромные отступы."""
    import re
    # Заменяем 2+ пустых строк на одну
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def publish_to_dzen(post: Post) -> bool:
    """Публикует пост в Yandex.Дзен через промежуточный Telegram‑канал.
    Дзен настроен на автоимпорт из этого канала.
    Особенности:
    - Первое предложение = заголовок статьи в Дзен (≤140 символов)
    - Двойные пустые строки сжимаются
    """
    # Создаём копию поста с компактным текстом для Дзена
    compact_post = Post(
        title=post.title[:140],  # Дзен берёт первую строку как заголовок, макс 140
        text=_compact_text(post.text),
        image_path=post.image_path,
        tags=post.tags,
        datetime=post.datetime,
        ready=post.ready,
    )
    return _send_tg(compact_post, DZEN_BRIDGE_CHANNEL_ID, label="Дзен‑мост (TG)")

# ---------------------------------------------------------------------------
# Одноклассники adapter
# ---------------------------------------------------------------------------
APP_ID = os.getenv("OK_APP_ID")
APP_PUBLIC_KEY = os.getenv("OK_APPLICATION_KEY")
APP_SECRET_KEY = os.getenv("OK_SECRET_KEY")
OK_ACCESS_TOKEN = os.getenv("OK_ACCESS_TOKEN")
OK_GROUP_ID = os.getenv("OK_GROUP_ID")  # числовой ID группы без знака «-»
OK_API_URL = "https://api.ok.ru/fb.do"

def _ok_signature(params: dict) -> str:
    """Формирует подпись запроса по алгоритму OK API (md5)."""
    base = "".join(f"{k}={v}" for k, v in sorted(params.items()))
    base += APP_SECRET_KEY or ""
    return hashlib.md5(base.encode("utf-8")).hexdigest()

def publish_to_ok(post: Post) -> bool:
    """Публикует пост в Одноклассники через REST‑API (mediatopic.post)."""
    if not all([APP_ID, APP_PUBLIC_KEY, APP_SECRET_KEY, OK_ACCESS_TOKEN, OK_GROUP_ID]):
        logging.warning("OK credentials missing – skipping OK publish.")
        return False
    text = f"{post.title}\n\n{post.text}"
    params = {
        "application_key": APP_PUBLIC_KEY,
        "method": "mediatopic.post",
        "gid": OK_GROUP_ID,
        "type": "GROUP_THEME",
        "text": text,
        "format": "json",
    }
    params["sig"] = _ok_signature(params)
    params["access_token"] = OK_ACCESS_TOKEN
    try:
        resp = requests.post(OK_API_URL, data=params, timeout=10)
        resp.raise_for_status()
        logging.info("✅ OK: пост опубликован.")
        return True
    except Exception as e:
        logging.error(f"❌ OK: ошибка публикации – {e}")
        return False
