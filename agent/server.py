import asyncio
import os
import uuid
from datetime import datetime
from typing import List, Optional

import requests
import uvicorn
from angelochka_core import get_answer
from bitrix_lead import create_lead
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from persistent_history import chat_db
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

TG_BOT_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("ORDERS_TG_CHAT_ID", "-1002212950101")  # группа/канал уведомлений

app = FastAPI(title="Angelochka AI Server v2")

# CORS: ограничиваем список доменов из .env
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://vezemcip.ru,https://www.vezemcip.ru,http://localhost:4321").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=True,
)


# --- Модели запросов ---

class ChatRequest(BaseModel):
    message: str
    session_id: str = ""


class LeadRequest(BaseModel):
    name: str
    phone: str = ""
    email: str = ""
    comment: str = ""


# --- VK Mini App: модель заказа ---
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


# --- Хранилище сессий (в памяти как фоллбэк) ---
sessions = {}
MAX_HISTORY = 20


@app.get("/")
async def root():
    return {
        "agent": "Анжелочка AI",
        "version": "2.0",
        "endpoints": {
            "chat": "POST /api/chat",
            "lead": "POST /api/lead",
            "health": "GET /api/health",
            "docs": "/docs"
        }
    }


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Чат с Анжелочкой. Поддерживает сессии для истории диалога."""
    try:
        session_id = request.session_id or str(uuid.uuid4())

        # Загружаем из облака, если доступно (передаем string, так как колонка TEXT)
        history = chat_db.load_history(user_id=str(session_id)) if chat_db._available else sessions.get(session_id, [])

        response = get_answer(request.message, history)

        # Сохраняем в облако или в память
        if chat_db._available:
            chat_db.save_message(user_id=str(session_id), role="user", content=request.message, user_name="web_user")
            chat_db.save_message(user_id=str(session_id), role="model", content=response, user_name="angelochka")
        else:
            # Фоллбэк в память
            history.append({"role": "user", "parts": [request.message]})
            history.append({"role": "model", "parts": [response]})
            sessions[session_id] = history[-MAX_HISTORY:]

        return {
            "response": response,
            "session_id": session_id
        }

    except Exception as e:
        # Логируем детали внутри сервера, но клиенту отдаём безопасную ошибку
        print(f"❌ Error in /api/chat: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Внутренняя ошибка сервера. Пожалуйста, попробуйте позже."
        )


import re as _re_server

# Прайс для расчёта суммы сделки
_PRICE_MAP = {
    "росс": 85, "росс-308": 85, "росс 308": 85,
    "кобб": 90, "кобб-500": 90, "кобб 500": 90,
    "бройлер": 85,  # дефолт = РОСС
    "мулард": 250, "агидель": 90,
    "индюк": 450, "индюшат": 450, "биг-6": 450, "хайбрид": 450,
    "гус": 320, "линдовск": 320,  # Обновлено 08.05 (из звонков)
    "несушк": 95, "ломан": 95, "хайсекс": 95,
    "доминант": 75,
    "мастер грей": 100, "ред бро": 100, "голошейк": 100,
}

def _estimate_deal_amount(context: str) -> float:
    """Оценивает сумму сделки из контекста диалога."""
    if not context:
        return 0
    
    ctx_lower = context.lower()
    
    # Ищем количество голов (используем findall, чтобы взять ПОСЛЕДНЕЕ совпадение - ответ пользователя)
    qty_matches = _re_server.findall(r'(\d{2,5})\s*(?:шт|голов|штук|цыплят|бройлер|утят|индюшат|гус)', ctx_lower)
    if not qty_matches:
        qty_matches = _re_server.findall(r'(?:хочу|нужно|закажу|заказ|бронь|заброниро)\s*(\d{2,5})', ctx_lower)
    
    qty = int(qty_matches[-1]) if qty_matches else 0
    
    # Определяем породу
    price_per_unit = 0
    for breed_key, price in _PRICE_MAP.items():
        if breed_key in ctx_lower:
            price_per_unit = price
            break
    
    if qty and price_per_unit:
        return qty * price_per_unit
    elif qty:
        return qty * 85  # дефолтная цена бройлера
    
    return 0


@app.post("/api/lead")
async def create_lead_endpoint(request: LeadRequest):
    """Создаёт лид в Битрикс24 CRM из заявки на сайте."""
    try:
        # Рассчитываем сумму сделки из контекста разговора
        amount = _estimate_deal_amount(request.comment)
        if amount > 0:
            print(f"💰 Оценка суммы сделки: {amount}₽")
        
        result = create_lead(
            name=request.name,
            phone=request.phone,
            email=request.email,
            comment=request.comment,
            source="WEB_CHAT",
            amount=amount if amount > 0 else None
        )
        if result["success"]:
            return {"success": True, "lead_id": result["lead_id"], "estimated_amount": amount}
        else:
            raise HTTPException(status_code=400, detail=result["error"])
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in /api/lead: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/vk-order")
async def vk_order(request: VkOrderRequest):
    """Принимает заказ из VK Mini App → создаёт лид в Битрикс24 → уведомляет в Telegram."""
    try:
        order_id = f"VK-{datetime.now().strftime('%d%m%y')}-{str(uuid.uuid4())[:6].upper()}"
        
        # Регионы: код → текст
        REGIONS = {
            "crimea": "Крым",
            "krasnodar": "Краснодарский край",
            "rostov": "Ростовская область",
            "stavropol": "Ставропольский край",
            "moscow": "Москва и МО",
            "pickup": "Самовывоз (пгт Азовское)",
        }
        region_label = REGIONS.get(request.region, request.region)
        
        # Формируем состав заказа
        items_text = ", ".join([
            f"{item.name} × {item.qty} шт ({item.price * item.qty:,}₽)"
            for item in request.items
        ]).replace(",", ",")
        
        comment = (
            f"📱 ЗАКАЗ ИЗ VK MINI APP\n"
            f"Номер заказа: {order_id}\n"
            f"VK ID: {request.user_id or 'неизвестен'}\n"
            f"Телефон: {request.phone}\n"
            f"Дата вывода: {request.delivery_date}\n"
            f"Регион: {region_label}\n"
            f"Состав: {items_text}\n"
            f"Итого: {request.total:,}₽ ({request.total_birds} голов)"
        )
        
        # 1. Создаём лид в Битрикс24
        lead_result = create_lead(
            name=request.user_name,
            phone=request.phone if request.phone != "не указан" else "",
            comment=comment,
            source="VK_MINI_APP",
            amount=float(request.total) if request.total else None,
            assigned_by_id=15  # Анжела Заботкина
        )
        
        lead_id = lead_result.get("lead_id", "?")
        print(f"✅ VK Order {order_id}: лид Битрикс #{lead_id}, сумма {request.total}₽")
        
        # 2. Уведомление в Telegram
        if TG_BOT_TOKEN:
            tg_text = (
                f"🛒 *Новый заказ из VK Mini App!*\n\n"
                f"👤 {request.user_name} | VK: {request.user_id or '—'}\n"
                f"📞 {request.phone}\n"
                f"📅 Дата вывода: `{request.delivery_date}`\n"
                f"🗺 Регион: {region_label}\n\n"
                f"*Состав заказа:*\n"
            )
            for item in request.items:
                tg_text += f"  • {item.name}: {item.qty} шт × {item.price}₽ = {item.qty * item.price:,}₽\n"
            tg_text += (
                f"\n💰 *Итого: {request.total:,}₽* ({request.total_birds} голов)\n"
                f"🔖 Заказ: `{order_id}`\n"
                f"📋 Лид Б24: #{lead_id}"
            )
            try:
                def send_tg():
                    return requests.post(
                        f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
                        json={"chat_id": TG_CHAT_ID, "text": tg_text, "parse_mode": "Markdown"},
                        timeout=10,
                        proxies={"http": None, "https": None}
                    )
                await asyncio.to_thread(send_tg)
            except Exception as tg_err:
                print(f"⚠️ TG уведомление не отправлено: {tg_err}")
        
        return {"success": True, "order_id": order_id, "lead_id": lead_id}
    
    except Exception as e:
        print(f"⚠️ Error in /api/vk-order: {e}")
        # Fallback: всегда возвращаем order_id даже при ошибке
        fallback_id = f"VK-{datetime.now().strftime('%d%m%y')}-{str(uuid.uuid4())[:6].upper()}"
        return {"success": False, "order_id": fallback_id, "error": str(e)}


@app.get("/api/health")
async def health():
    return {"status": "ok", "agent": "angelochka", "version": "2.0"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
