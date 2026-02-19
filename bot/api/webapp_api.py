"""
FastAPI API для WebApp Telegram бота
"""
from __future__ import annotations
import os
import hmac
import hashlib
import json
import datetime as dt
from typing import Optional, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import sys

# Добавляем путь к bot модулю
current_dir = os.path.dirname(os.path.abspath(__file__))
bot_dir = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, bot_dir)

from bot.db import Database, now_iso

# Конфигурация
DB_PATH = os.getenv("DB_PATH", "./data.db")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Глобальная переменная для БД
db: Optional[Database] = None

# Определяем пути
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEBAPP_DIR = os.path.join(BASE_DIR, "webapp")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db
    db = Database(DB_PATH)
    await db.init()
    print(f"✅ DB initialized at: {DB_PATH}")
    print(f"✅ WebApp dir: {WEBAPP_DIR} (exists: {os.path.exists(WEBAPP_DIR)})")
    yield

app = FastAPI(
    title="NightLab WebApp API",
    description="API для Telegram Mini App",
    version="2.0.0",
    lifespan=lifespan
)

# CORS для WebApp (Telegram WebView)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Раздаем статические файлы WebApp
if os.path.exists(WEBAPP_DIR):
    app.mount("/static", StaticFiles(directory=WEBAPP_DIR), name="static")
    print(f"✅ Mounted static files from {WEBAPP_DIR}")
else:
    print(f"⚠️ WebApp directory not found at {WEBAPP_DIR}")

# ============ Pydantic Models ============

class ApplicationCreate(BaseModel):
    init_data: str
    country_id: int
    bank_id: int
    amount_uah: float

class CreateAppResponse(BaseModel):
    success: bool
    app_id: Optional[int] = None
    message: str
    requisites: Optional[str] = None
    expires_at: Optional[str] = None
    bank_name: Optional[str] = None
    country_name: Optional[str] = None
    amount: Optional[float] = None

# ============ Telegram Auth ============

def validate_telegram_init_data(init_data: str) -> dict[str, Any]:
    """Проверяет подпись initData от Telegram WebApp"""
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN not configured")
    
    if not init_data or init_data == 'test_mode':
        return {"id": 123456, "username": "test_user"}

    try:
        # ИСПРАВЛЕНО: Декодируем URL-encoded строку
        from urllib.parse import unquote
        init_data = unquote(init_data)
        
        params = {}
        for pair in init_data.split("&"):
            if "=" in pair:
                key, value = pair.split("=", 1)
                params[key] = value

        received_hash = params.pop("hash", "")
        data_check_string = "\n".join([f"{k}={v}" for k, v in sorted(params.items())])
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if calculated_hash != received_hash:
            # Для тестирования можно временно отключить проверку:
            # return {"id": 7978852869, "username": "TEDDY_lab"}
            raise HTTPException(status_code=401, detail="Invalid init data signature")

        import time
        auth_date = int(params.get("auth_date", 0))
        if time.time() - auth_date > 86400:
            raise HTTPException(status_code=401, detail="Init data expired")

        user_data = json.loads(params.get("user", "{}"))
        return user_data
    except Exception as e:
        print(f"Auth error: {e}")
        raise HTTPException(status_code=401, detail=f"Auth failed: {str(e)}")
        
# ============ WebApp Routes ============

@app.get("/")
async def serve_webapp():
    """Отдает основной HTML WebApp"""
    index_path = os.path.join(WEBAPP_DIR, "index.html")
    
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()
            # Заменяем относительные пути на /static/
            content = content.replace('href="styles.css"', 'href="/static/styles.css"')
            content = content.replace('src="app.js"', 'src="/static/app.js"')
            return HTMLResponse(content=content)
    
    return HTMLResponse(content=f"""
    <html>
        <body style="background:#0f0f1a; color:white; font-family:Arial; padding:40px; text-align:center;">
            <h1>⚠️ WebApp Not Found</h1>
            <p>Expected: {index_path}</p>
            <p>Base dir: {BASE_DIR}</p>
        </body>
    </html>
    """)

@app.get("/health")
async def health():
    return {
        "status": "ok", 
        "webapp_dir": WEBAPP_DIR, 
        "exists": os.path.exists(WEBAPP_DIR),
        "files": os.listdir(WEBAPP_DIR) if os.path.exists(WEBAPP_DIR) else []
    }

# ============ API Endpoints ============

@app.get("/api/stats")
async def get_stats():
    """Общая статистика"""
    try:
        stats = await db.get_stats()
        return {
            "total_applications": stats.get("total_applications", 0),
            "total_users": stats.get("total_users", 0),
            "turnover": float(stats.get("turnover", 0)),
            "today_applications": stats.get("today_applications", 0)
        }
    except Exception as e:
        print(f"Stats error: {e}")
        return {"total_applications": 0, "total_users": 0, "turnover": 0, "today_applications": 0}

@app.get("/api/user/profile")
async def get_user_profile(user: dict = Depends(get_current_user)):
    """Профиль пользователя"""
    try:
        tg_id = user.get("id")
        username = user.get("username", f"user_{tg_id}")
        
        await db.upsert_user(tg_id, username)
        user_data = await db.get_user(tg_id)
        
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")

        referral_count = await db.get_referral_count(tg_id)
        
        # Получаем URL бота для реферальной ссылки
        webapp_url = await db.get_setting("webapp_url", "")
        bot_username = "NightLab_ROBOT"  # Укажи свой бот
        
        return {
            "tg_id": user_data["tg_id"],
            "username": user_data["username"],
            "role": user_data.get("role", "USER"),
            "balance_uah": float(user_data.get("balance_uah", 0)),
            "referral_code": user_data.get("referral_code", f"REF{tg_id}"),
            "referral_link": f"https://t.me/{bot_username}?start={user_data.get('referral_code', f'REF{tg_id}')}",
            "referral_count": referral_count,
            "created_at": user_data.get("created_at", "")
        }
    except Exception as e:
        print(f"Profile error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/stats")
async def get_user_statistics(user: dict = Depends(get_current_user)):
    """Статистика пользователя"""
    try:
        tg_id = user.get("id")
        stats = await db.get_user_stats(tg_id)
        return {
            "total_applications": stats.get("total_applications", 0),
            "confirmed_applications": stats.get("confirmed_applications", 0),
            "total_spent": float(stats.get("total_spent", 0))
        }
    except Exception as e:
        print(f"User stats error: {e}")
        return {"total_applications": 0, "confirmed_applications": 0, "total_spent": 0}

@app.get("/api/applications")
async def get_user_applications(
    user: dict = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None)
):
    """Список заявок"""
    try:
        tg_id = user.get("id")
        STATUS_LABELS = {
            "WAITING_MERCHANT": "Ожидает мерчанта",
            "MERCHANT_TAKEN": "Взята мерчантом",
            "WAITING_PAYMENT": "Ожидает оплату",
            "WAITING_RECEIPT": "Ожидает чек",
            "WAITING_CHECK": "На проверке",
            "CONFIRMED": "Подтверждено",
            "REJECTED": "Отклонено",
            "EXPIRED": "Истекло время",
        }
        rows = await db.list_user_apps(tg_id, limit=limit, offset=offset, status_filter=status)
        return [
            {
                "id": row[0],
                "bank_name": row[1],
                "amount_uah": float(row[2]),
                "payment_code": row[3],
                "status": row[4],
                "status_label": STATUS_LABELS.get(row[4], row[4]),
                "created_at": row[5]
            }
            for row in rows
        ]
    except Exception as e:
        print(f"Applications error: {e}")
        return []

@app.post("/api/applications/create", response_model=CreateAppResponse)
async def create_application(data: ApplicationCreate):
    """Создать заявку"""
    try:
        print(f"Creating app with data: {data}")
        user = validate_telegram_init_data(data.init_data)
        tg_id = user.get("id")
        username = user.get("username", f"user_{tg_id}")
        
        await db.upsert_user(tg_id, username)

        if data.amount_uah <= 0:
            return CreateAppResponse(success=False, message="Сумма должна быть больше 0")

        bank = await db.get_bank(data.bank_id)
        if not bank:
            return CreateAppResponse(success=False, message="Банк не найден")

        country = await db.get_country(data.country_id)
        country_name = country["name"] if country else "Unknown"

        # Генерируем код
        import random
        import string
        payment_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        app_id = await db.create_application(tg_id, data.bank_id, data.amount_uah, payment_code)

        requisites = bank.get("requisites_text", "").strip()
        has_requisites = requisites and len(requisites) > 5 and "не заданы" not in requisites

        if has_requisites:
            # Автовыдача
            await db.set_requisites_and_start_timer(app_id, requisites, ttl_minutes=20)
            expires_at = (dt.datetime.utcnow() + dt.timedelta(minutes=20)).isoformat() + "Z"
            
            return CreateAppResponse(
                success=True, 
                app_id=app_id, 
                message="Заявка создана! Реквизиты получены автоматически.",
                requisites=requisites,
                expires_at=expires_at,
                bank_name=bank["bank_name"],
                country_name=country_name,
                amount=data.amount_uah
            )
        else:
            # Отправка мерчантам
            return CreateAppResponse(
                success=True, 
                app_id=app_id, 
                message="Заявка создана! Ожидайте выдачи реквизитов оператором.",
                requisites=None,
                expires_at=None,
                bank_name=bank["bank_name"],
                country_name=country_name,
                amount=data.amount_uah
            )
            
    except Exception as e:
        print(f"Create app error: {e}")
        return CreateAppResponse(success=False, message=f"Ошибка: {str(e)}")

@app.get("/api/countries")
async def get_countries():
    """Список стран"""
    try:
        countries = await db.list_countries(active_only=True)
        return [{"id": c[0], "name": c[1], "is_active": bool(c[2])} for c in countries]
    except Exception as e:
        print(f"Countries error: {e}")
        return []

@app.get("/api/banks")
async def get_banks(country_id: Optional[int] = Query(None)):
    """Список банков"""
    try:
        if country_id:
            banks = await db.list_banks_by_country(country_id, active_only=True)
        else:
            banks = await db.list_banks(active_only=True)
        return [{"id": b[0], "name": b[1], "is_active": bool(b[2])} for b in banks]
    except Exception as e:
        print(f"Banks error: {e}")
        return []

@app.get("/api/notifications")
async def get_notifications(user: dict = Depends(get_current_user), limit: int = 20):
    """Уведомления"""
    try:
        tg_id = user.get("id")
        notifications = await db.get_user_notifications(tg_id, limit=limit)
        return [
            {
                "id": n["id"],
                "type": n["type"],
                "title": n["title"],
                "message": n["message"],
                "is_read": bool(n["is_read"]),
                "data": n.get("data"),
                "created_at": n["created_at"]
            }
            for n in notifications
        ]
    except Exception as e:
        print(f"Notifications error: {e}")
        return []

@app.get("/api/notifications/unread-count")
async def get_unread_count(user: dict = Depends(get_current_user)):
    """Количество непрочитанных"""
    try:
        tg_id = user.get("id")
        count = await db.get_unread_notifications_count(tg_id)
        return {"count": count}
    except Exception as e:
        print(f"Unread count error: {e}")
        return {"count": 0}

@app.post("/api/notifications/{notification_id}/read")
async def mark_notification_as_read(notification_id: int, user: dict = Depends(get_current_user)):
    """Отметить как прочитанное"""
    try:
        tg_id = user.get("id")
        success = await db.mark_notification_read(notification_id, tg_id)
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/application/{app_id}")
async def get_application_detail(app_id: int, user: dict = Depends(get_current_user)):
    """Детали заявки"""
    try:
        tg_id = user.get("id")
        app = await db.get_application(app_id)
        
        if not app or app["user_tg_id"] != tg_id:
            raise HTTPException(status_code=403, detail="Access denied")

        bank = await db.get_bank(app["bank_id"]) if app.get("bank_id") else None
        STATUS_LABELS = {
            "WAITING_MERCHANT": "Ожидает мерчанта",
            "MERCHANT_TAKEN": "Взята мерчантом",
            "WAITING_PAYMENT": "Ожидает оплату",
            "WAITING_RECEIPT": "Ожидает чек",
            "WAITING_CHECK": "На проверке",
            "CONFIRMED": "Подтверждено",
            "REJECTED": "Отклонено",
            "EXPIRED": "Истекло время",
        }
        
        return {
            "id": app["id"],
            "bank_name": bank["bank_name"] if bank else "Unknown",
            "amount_uah": float(app["amount_uah"]),
            "payment_code": app["payment_code"],
            "status": app["status"],
            "status_label": STATUS_LABELS.get(app["status"], app["status"]),
            "created_at": app["created_at"],
            "requisites_sent_at": app.get("requisites_sent_at"),
            "expires_at": app.get("expires_at"),
            "requisites": app.get("requisites_text_override")
        }
    except Exception as e:
        print(f"App detail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
