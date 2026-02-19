from __future__ import annotations
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import load_config
from bot.db import Database
from bot.notifications import NotificationManager

from bot.handlers.user import router as user_router
from bot.handlers.apps import router as apps_router
from bot.handlers.merchant import router as merchant_router
from bot.handlers.payments import router as payments_router
from bot.handlers.admin import router as admin_router
from bot.handlers.chat import router as chat_router

async def _expire_loop(bot: Bot, db: Database, logger: logging.Logger):
    """Цикл проверки истекших заявок"""
    notif_manager = NotificationManager(bot, db)
    
    while True:
        try:
            expired_ids = await db.expire_overdue()
            for app_id in expired_ids:
                app = await db.get_application(app_id)
                if app:
                    # Отправляем уведомление пользователю
                    await notif_manager.notify_app_expired(app_id, app["user_tg_id"])
                    
                    try:
                        await bot.send_message(
                            app["user_tg_id"], 
                            f"⏳ Заявка #{app_id} закрыта автоматически (не нажали «Я оплатил» за 20 минут)."
                        )
                    except Exception:
                        pass
            if expired_ids:
                logger.info("Expired apps: %s", expired_ids)
        except Exception as e:
            logger.exception("expire loop error: %s", e)
        await asyncio.sleep(30)

async def _notification_loop(bot: Bot, db: Database, logger: logging.Logger):
    """Цикл обработки уведомлений"""
    notif_manager = NotificationManager(bot, db)
    
    while True:
        try:
            # Здесь можно добавить логику для периодических уведомлений
            # Например, напоминания о неоплаченных заявках
            pass
        except Exception as e:
            logger.exception("notification loop error: %s", e)
        await asyncio.sleep(60)

async def _run():
    config = load_config()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()],
    )
    logger = logging.getLogger("paydesk")

    bot = Bot(token=config.bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    db = Database(config.db_path)
    await db.init()

    # seed countries if empty
    countries = await db.list_countries(active_only=False)
    if not countries:
        await db.upsert_country("Украина")
        default_country_id = (await db.list_countries(active_only=False))[0][0]

        # seed banks if empty and link to default country
        banks = await db.list_banks(active_only=False)
        if not banks:
            await db.upsert_bank("Моно Банк", "Карта: ....\nФИО: ....\nНазначение: ....", default_country_id)
            await db.upsert_bank("Приват Банк", "Карта: ....\nФИО: ....\nНазначение: ....", default_country_id)

    # Include routers
    dp.include_router(user_router)
    dp.include_router(apps_router)
    dp.include_router(merchant_router)
    dp.include_router(payments_router)
    dp.include_router(admin_router)
    dp.include_router(chat_router)

    # Start background tasks
    asyncio.create_task(_expire_loop(bot, db, logger))
    asyncio.create_task(_notification_loop(bot, db, logger))

    logger.info("Bot v5.0 started with WebApp support")
    await dp.start_polling(bot, config=config, db=db, logger=logger)

def main():
    asyncio.run(_run())

if __name__ == "__main__":
    main()
