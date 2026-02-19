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
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import Database, now_iso

# Конфигурация
DB_PATH = os.getenv("DB_PATH", "./data.db")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Глобальная переменная для БД
db: Optional[Database] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db
    db = Database(DB_PATH)
    await db.init()
    yield
    # Cleanup


app = FastAPI(
    title="NightLab WebApp API",
    description="API для Telegram Mini App",
    version="1.0.0",
    lifespan=lifespan
)

# CORS для WebApp
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Раздаем статические файлы WebApp (если они рядом с ботом)
# Предполагаем что папка webapp в корне проекта
webapp_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "webapp")
if os.path.exists(webapp_path):
    app.mount("/static", StaticFiles(directory=webapp_path), name="static")

@app.get("/")
async def serve_webapp():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>NightLab</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            body { background: #0a0a0f; color: white; font-family: Arial; padding: 20px; }
            .btn { background: #a855f7; color: white; padding: 15px; border-radius: 10px; 
                   text-align: center; margin: 10px 0; cursor: pointer; }
        </style>
    </head>
    <body>
        <h1>🌙 NightLab</h1>
        <div class="btn" onclick="tg.openTelegramLink('https://t.me/NightLab_ROBOT')">Открыть бота</div>
        <div id="data"></div>
        <script>
            const tg = window.Telegram.WebApp;
            tg.expand();
            fetch('/api/stats')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('data').innerHTML = 
                        '<p>Всего заявок: ' + data.total_applications + '</p>';
                });
        </script>
    </body>
    </html>
    """
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html_content)
    

# ============ Модели Pydantic ============

class UserProfile(BaseModel):
    tg_id: int
    username: str
    role: str
    balance_uah: float
    referral_code: str
    referral_link: str
    referral_count: int
    created_at: str


class ApplicationCreate(BaseModel):
    init_data: str
    country_id: int
    bank_id: int
    amount_uah: float


class ApplicationResponse(BaseModel):
    id: int
    bank_name: str
    amount_uah: float
    payment_code: str
    status: str
    status_label: str
    created_at: str


class StatsResponse(BaseModel):
    total_applications: int
    total_users: int
    turnover: float
    today_applications: int


class UserStatsResponse(BaseModel):
    total_applications: int
    confirmed_applications: int
    total_spent: float


class NotificationResponse(BaseModel):
    id: int
    type: str
    title: str
    message: str
    is_read: bool
    data: Optional[str]
    created_at: str


class CreateAppResponse(BaseModel):
    success: bool
    app_id: Optional[int] = None
    message: str
    requisites: Optional[str] = None
    expires_at: Optional[str] = None
    bank_name: Optional[str] = None
    country_name: Optional[str] = None
    amount: Optional[float] = None


# ============ Проверка Telegram initData ============

def validate_telegram_init_data(init_data: str) -> dict[str, Any]:
    """Проверяет подпись initData от Telegram WebApp"""
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN not configured")

    # Parse init_data
    params = {}
    for pair in init_data.split("&"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            params[key] = value

    received_hash = params.pop("hash", "")

    # Create data_check_string
    data_check_string = "\n".join([f"{k}={v}" for k, v in sorted(params.items())])

    # Create secret key
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()

    # Calculate hash
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if calculated_hash != received_hash:
        raise HTTPException(status_code=401, detail="Invalid init data signature")

    # Check auth_date is recent (within 24 hours)
    import time
    auth_date = int(params.get("auth_date", 0))
    if time.time() - auth_date > 86400:
        raise HTTPException(status_code=401, detail="Init data expired")

    # Parse user data
    user_data = json.loads(params.get("user", "{}"))
    return user_data


async def get_current_user(x_init_data: str = Header(..., alias="X-Init-Data")) -> dict[str, Any]:
    """Dependency для получения текущего пользователя"""
    return validate_telegram_init_data(x_init_data)


# ============ Endpoints ============

@app.get("/")
async def root():
    return {"status": "ok", "service": "NightLab WebApp API"}


@app.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    """Получить общую статистику платформы"""
    stats = await db.get_stats()
    return StatsResponse(**stats)


@app.get("/api/user/profile", response_model=UserProfile)
async def get_user_profile(user: dict = Depends(get_current_user)):
    """Получить профиль пользователя"""
    tg_id = user.get("id")
    username = user.get("username", f"user_{tg_id}")

    # Ensure user exists
    await db.upsert_user(tg_id, username)

    user_data = await db.get_user(tg_id)
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")

    referral_count = await db.get_referral_count(tg_id)

    # Get webapp URL from settings
    webapp_url = await db.get_setting("webapp_url", "https://t.me/your_bot/webapp")
    bot_username = webapp_url.split("/")[3] if "/" in webapp_url else "your_bot"

    return UserProfile(
        tg_id=user_data["tg_id"],
        username=user_data["username"],
        role=user_data["role"],
        balance_uah=user_data["balance_uah"],
        referral_code=user_data["referral_code"],
        referral_link=f"https://t.me/{bot_username}?start={user_data['referral_code']}",
        referral_count=referral_count,
        created_at=user_data["created_at"]
    )


@app.get("/api/user/stats", response_model=UserStatsResponse)
async def get_user_statistics(user: dict = Depends(get_current_user)):
    """Получить статистику пользователя"""
    tg_id = user.get("id")
    stats = await db.get_user_stats(tg_id)
    return UserStatsResponse(**stats)


@app.get("/api/applications", response_model=list[ApplicationResponse])
async def get_user_applications(
        user: dict = Depends(get_current_user),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        status: Optional[str] = Query(None)
):
    """Получить список заявок пользователя"""
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
        ApplicationResponse(
            id=row[0],
            bank_name=row[1],
            amount_uah=row[2],
            payment_code=row[3],
            status=row[4],
            status_label=STATUS_LABELS.get(row[4], row[4]),
            created_at=row[5]
        )
        for row in rows
    ]


@app.get("/api/applications/count")
async def get_applications_count(
        user: dict = Depends(get_current_user),
        status: Optional[str] = Query(None)
):
    """Получить количество заявок пользователя"""
    tg_id = user.get("id")
    count = await db.count_user_apps(tg_id, status_filter=status)
    return {"count": count}


@app.post("/api/applications/create", response_model=CreateAppResponse)
async def create_application(data: ApplicationCreate):
    """Создать новую заявку"""
    user = validate_telegram_init_data(data.init_data)
    tg_id = user.get("id")
    username = user.get("username", f"user_{tg_id}")

    # Ensure user exists
    await db.upsert_user(tg_id, username)

    # Validate amount
    if data.amount_uah <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    # Check bank exists
    bank = await db.get_bank(data.bank_id)
    if not bank:
        raise HTTPException(status_code=404, detail="Bank not found")

    # Get country name
    country = await db.get_country(data.country_id)
    country_name = country["name"] if country else "Unknown"

    # Generate payment code
    from utils import gen_payment_code
    payment_code = gen_payment_code()

    # Create application
    app_id = await db.create_application(tg_id, data.bank_id, data.amount_uah, payment_code)

    # Check if bank has auto-requisites
    requisites = bank.get("requisites_text", "").strip()
    has_requisites = requisites and len(requisites) > 5 and "не заданы" not in requisites

    if has_requisites:
        # Auto-assign requisites
        await db.set_requisites_and_start_timer(app_id, requisites, ttl_minutes=20)

        # Create notification
        await db.create_notification(
            tg_id,
            "requisites",
            "Реквизиты получены",
            f"Заявка #{app_id}: реквизиты для оплаты",
            json.dumps({"app_id": app_id})
        )

        return CreateAppResponse(
            success=True,
            app_id=app_id,
            message="Заявка создана! Реквизиты получены автоматически.",
            requisites=requisites,
            expires_at=(dt.datetime.utcnow() + dt.timedelta(minutes=20)).isoformat() + "Z",
            bank_name=bank["bank_name"],
            country_name=country_name,
            amount=data.amount_uah
        )
    else:
        # Send to merchant chat
        merchant_chat_id = await db.get_setting("merchant_chat_id")
        if merchant_chat_id:
            # Notification will be sent by bot handler
            pass

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


@app.get("/api/countries")
async def get_countries():
    """Получить список стран"""
    countries = await db.list_countries(active_only=True)
    return [
        {"id": c[0], "name": c[1], "is_active": bool(c[2])}
        for c in countries
    ]


@app.get("/api/banks")
async def get_banks(country_id: Optional[int] = Query(None)):
    """Получить список банков"""
    if country_id:
        banks = await db.list_banks_by_country(country_id, active_only=True)
    else:
        banks = await db.list_banks(active_only=True)

    return [
        {"id": b[0], "name": b[1], "is_active": bool(b[2])}
        for b in banks
    ]


@app.get("/api/notifications", response_model=list[NotificationResponse])
async def get_notifications(
        user: dict = Depends(get_current_user),
        limit: int = Query(20, ge=1, le=100)
):
    """Получить уведомления пользователя"""
    tg_id = user.get("id")
    notifications = await db.get_user_notifications(tg_id, limit=limit)
    return [
        NotificationResponse(
            id=n["id"],
            type=n["type"],
            title=n["title"],
            message=n["message"],
            is_read=n["is_read"],
            data=n["data"],
            created_at=n["created_at"]
        )
        for n in notifications
    ]


@app.get("/api/notifications/unread-count")
async def get_unread_count(user: dict = Depends(get_current_user)):
    """Получить количество непрочитанных уведомлений"""
    tg_id = user.get("id")
    count = await db.get_unread_notifications_count(tg_id)
    return {"count": count}


@app.post("/api/notifications/{notification_id}/read")
async def mark_notification_as_read(notification_id: int, user: dict = Depends(get_current_user)):
    """Отметить уведомление как прочитанное"""
    tg_id = user.get("id")
    success = await db.mark_notification_read(notification_id, tg_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True}


@app.get("/api/application/{app_id}")
async def get_application_detail(app_id: int, user: dict = Depends(get_current_user)):
    """Получить детали заявки"""
    tg_id = user.get("id")
    app = await db.get_application(app_id)

    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if app["user_tg_id"] != tg_id:
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
        "amount_uah": app["amount_uah"],
        "payment_code": app["payment_code"],
        "status": app["status"],
        "status_label": STATUS_LABELS.get(app["status"], app["status"]),
        "created_at": app["created_at"],
        "requisites_sent_at": app["requisites_sent_at"],
        "expires_at": app["expires_at"],
        "requisites": app["requisites_text_override"]
    }


# ============ Запуск ============

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
