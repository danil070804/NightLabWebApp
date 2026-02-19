from __future__ import annotations
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from bot.handlers.user import ensure_subscribed

router = Router()

async def safe_answer(call: CallbackQuery):
    """Безопасный ответ на callback query"""
    try:
        await call.answer()
    except TelegramBadRequest:
        pass

STATUS_META = {
    "WAITING_MERCHANT": ("🟡", "Ожидает мерчанта"),
    "MERCHANT_TAKEN": ("🟡", "Взята мерчантом"),
    "WAITING_PAYMENT": ("🟡", "Ожидает оплату"),
    "WAITING_RECEIPT": ("🟡", "Ожидает чек"),
    "WAITING_CHECK": ("🟡", "На проверке"),
    "CONFIRMED": ("🟢", "Подтверждено"),
    "REJECTED": ("🔴", "Отклонено"),
    "EXPIRED": ("🔴", "Истекло время"),
}

def format_status(status: str) -> str:
    emoji, label = STATUS_META.get(status, ("⚪️", status))
    return f"{emoji} {label}"

@router.message(F.text.in_({"📄 Мои заявки", "Мои заявки"}))
async def my_apps(message: Message, db, config):
    if not await ensure_subscribed(message, message.bot, config, db):
        return
    rows = await db.list_user_apps(message.from_user.id)
    if not rows:
        await message.answer("У вас пока нет заявок.")
        return

    lines = []
    for app_id, bank_name, amount, code, status, created_at in rows:
        lines.append(
            f"#{app_id} | {bank_name} | {amount:.2f} грн | {code} | {format_status(status)} | {created_at[:10]}"
        )
    
    # Разбиваем на части если слишком длинное сообщение
    text = "Ваши заявки (последние 20):\n" + "\n".join(lines)
    if len(text) > 4000:
        parts = []
        current_part = "Ваши заявки:\n"
        for line in lines:
            if len(current_part) + len(line) + 1 > 4000:
                parts.append(current_part)
                current_part = line + "\n"
            else:
                current_part += line + "\n"
        parts.append(current_part)
        
        for part in parts:
            await message.answer(part)
    else:
        await message.answer(text)

@router.callback_query(F.data == "my_apps")
async def my_apps_callback(call: CallbackQuery, db, config):
    """Callback для кнопки 'Мои заявки'"""
    await safe_answer(call)
    
    rows = await db.list_user_apps(call.from_user.id)
    if not rows:
        await call.message.answer("У вас пока нет заявок.")
        return

    lines = []
    for app_id, bank_name, amount, code, status, created_at in rows:
        lines.append(
            f"#{app_id} | {bank_name} | {amount:.2f} грн | {code} | {format_status(status)} | {created_at[:10]}"
        )
    
    await call.message.answer("Ваши заявки (последние 20):\n" + "\n".join(lines))
