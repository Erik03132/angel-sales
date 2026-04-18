import os
import uuid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from angelochka_core import get_answer
from bitrix_lead import create_lead

app = FastAPI(title="Angelochka AI Server v2")

# CORS: разрешаем запросы от Astro dev-сервера и любого продакшн-домена
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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


# --- Хранилище сессий (в памяти) ---
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

        if session_id not in sessions:
            sessions[session_id] = []

        history = sessions[session_id]
        response = get_answer(request.message, history)

        # Обновляем историю
        history.append({"role": "user", "parts": [request.message]})
        history.append({"role": "model", "parts": [response]})
        sessions[session_id] = history[-MAX_HISTORY:]

        return {
            "response": response,
            "session_id": session_id
        }

    except Exception as e:
        print(f"Error in /api/chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/lead")
async def create_lead_endpoint(request: LeadRequest):
    """Создаёт лид в Битрикс24 CRM из заявки на сайте."""
    try:
        result = create_lead(
            name=request.name,
            phone=request.phone,
            email=request.email,
            comment=request.comment,
            source="WEB_CHAT"
        )
        if result["success"]:
            return {"success": True, "lead_id": result["lead_id"]}
        else:
            raise HTTPException(status_code=400, detail=result["error"])
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in /api/lead: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health():
    return {"status": "ok", "agent": "angelochka", "version": "2.0"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
