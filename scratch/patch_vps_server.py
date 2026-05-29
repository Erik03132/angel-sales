#!/usr/bin/env python3
"""Патч VPS server.py: добавляет /api/vk-order endpoint."""

SERVER_PATH = "/root/antigravity/angel-backend/server.py"

with open(SERVER_PATH, "r") as f:
    content = f.read()

# Бэкап
with open(SERVER_PATH + ".bak_vkorder", "w") as f:
    f.write(content)

# === 1. Добавляем импорты ===
import_block = """import json
import requests as _requests_vk
from datetime import datetime
from typing import List, Optional
from dotenv import load_dotenv

# VK Order: env для TG уведомлений
_BASE_DIR_VK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_BASE_DIR_VK, ".env"), override=True)
TG_BOT_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN", "")
TG_ORDERS_CHAT = os.getenv("ORDERS_TG_CHAT_ID", "176203333")
"""

content = content.replace(
    "from persistent_history import chat_db\n",
    "from persistent_history import chat_db\n" + import_block + "\n",
    1
)

# === 2. Добавляем VK модели ===
vk_models = '''
# --- VK Mini App: модели заказа ---
class VkOrderItem(BaseModel):
    name: str
    qty: int
    price: int

class VkOrderRequest(BaseModel):
    user_name: str = "VK User"
    user_id: Optional[int] = None
    phone: str = "не указан"
    items: List[VkOrderItem] = []
    total: int = 0
    total_birds: int = 0
    delivery_date: str = ""
    region: str = ""
    source: str = "vk_mini_app"

'''

content = content.replace(
    "# --- Хранилище сессий",
    vk_models + "# --- Хранилище сессий",
    1
)

# === 3. Добавляем vk_order в root endpoint ===
content = content.replace(
    '"docs": "/docs"',
    '"vk_order": "POST /api/vk-order",\n            "docs": "/docs"',
    1
)

# === 4. Добавляем endpoint ===
vk_endpoint = '''
@app.post("/api/vk-order")
async def vk_order(request: VkOrderRequest):
    """Принимает заказ из VK Mini App -> Битрикс24 лид + TG уведомление."""
    try:
        order_id = f"VK-{datetime.now().strftime('%d%m%y')}-{str(uuid.uuid4())[:6].upper()}"

        REGIONS = {
            "crimea": "Крым", "krasnodar": "Краснодарский край",
            "rostov": "Ростовская область", "stavropol": "Ставропольский край",
            "moscow": "Москва и МО", "pickup": "Самовывоз (пгт Азовское)",
        }
        region_label = REGIONS.get(request.region, request.region)

        items_text = ", ".join([
            f"{item.name} x {item.qty} шт ({item.price * item.qty}р)"
            for item in request.items
        ])

        comment = (
            f"\\U0001f4f1 ЗАКАЗ ИЗ VK MINI APP\\n"
            f"Номер: {order_id}\\n"
            f"VK ID: {request.user_id or 'неизвестен'}\\n"
            f"Тел: {request.phone}\\n"
            f"Дата: {request.delivery_date}\\n"
            f"Регион: {region_label}\\n"
            f"Состав: {items_text}\\n"
            f"Итого: {request.total}р ({request.total_birds} голов)"
        )

        lead_result = create_lead(
            name=request.user_name,
            phone=request.phone if request.phone != "не указан" else "",
            comment=comment,
            source="VK_MINI_APP",
            amount=float(request.total) if request.total else None,
        )

        lead_id = lead_result.get("lead_id", "?")
        print(f"\\u2705 VK Order {order_id}: лид Б24 #{lead_id}, сумма {request.total}р")

        if TG_BOT_TOKEN:
            tg_text = (
                f"\\U0001f6d2 *Заказ из VK Mini App!*\\n\\n"
                f"\\U0001f464 {request.user_name} | VK: {request.user_id or '—'}\\n"
                f"\\U0001f4de {request.phone}\\n"
                f"\\U0001f4c5 Дата: {request.delivery_date}\\n"
                f"\\U0001f5fa Регион: {region_label}\\n\\n"
                f"*Состав:*\\n"
            )
            for item in request.items:
                tg_text += f"  \\u2022 {item.name}: {item.qty} шт x {item.price}р = {item.qty * item.price}р\\n"
            tg_text += (
                f"\\n\\U0001f4b0 *Итого: {request.total}р* ({request.total_birds} голов)\\n"
                f"\\U0001f516 Заказ: `{order_id}`\\n"
                f"\\U0001f4cb Лид Б24: #{lead_id}"
            )
            try:
                _requests_vk.post(
                    f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
                    json={"chat_id": TG_ORDERS_CHAT, "text": tg_text, "parse_mode": "Markdown"},
                    timeout=10, proxies={"http": None, "https": None}
                )
            except Exception as tg_err:
                print(f"\\u26a0\\ufe0f TG уведомление не отправлено: {tg_err}")

        return {"success": True, "order_id": order_id, "lead_id": lead_id}

    except Exception as e:
        print(f"\\u26a0\\ufe0f Error in /api/vk-order: {e}")
        fallback_id = f"VK-{datetime.now().strftime('%d%m%y')}-{str(uuid.uuid4())[:6].upper()}"
        return {"success": False, "order_id": fallback_id, "error": str(e)}

'''

content = content.replace(
    '@app.get("/api/health")',
    vk_endpoint + '@app.get("/api/health")',
    1
)

with open(SERVER_PATH, "w") as f:
    f.write(content)

print("✅ Patch applied successfully!")
print(f"   Backup: {SERVER_PATH}.bak_vkorder")
