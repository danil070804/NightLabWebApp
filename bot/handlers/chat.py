from __future__ import annotations
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from bot.states import ChatFlow

router = Router()

async def safe_answer(call: CallbackQuery):
    """Безопасный ответ на callback query"""
    try:
        await call.answer()
    except TelegramBadRequest:
        pass

@router.callback_query(F.data.startswith("chat:"))
async def chat_callback(call: CallbackQuery, state: FSMContext, db):
    await safe_answer(call)
    app_id = int(call.data.split(":")[1])
    
    app = await db.get_application(app_id)
    if not app:
        await call.message.answer("Заявка не найдена.")
        return
    
    # Определяем, кто инициирует чат
    is_user = call.from_user.id == app["user_tg_id"]
    is_merchant = call.from_user.id == app.get("assigned_merchant_tg_id")
    
    if not (is_user or is_merchant):
        # Админ может писать всем
        role = await db.get_user_role(call.from_user.id)
        if role != "ADMIN":
            await call.message.answer("Нет доступа к этому чату.")
            return
    
    await state.set_state(ChatFlow.chatting)
    await state.update_data(
        chat_app_id=app_id,
        chat_partner_id=app["user_tg_id"] if not is_user else app.get("assigned_merchant_tg_id")
    )
    
    await call.message.answer(
        f"💬 Чат по заявке #{app_id}\n\n"
        f"Отправьте сообщение. Для выхода напишите /exit"
    )

@router.message(ChatFlow.chatting)
async def chat_message(message: Message, state: FSMContext, db, bot):
    if message.text == "/exit":
        await state.clear()
        await message.answer("💬 Чат завершен.")
        return
    
    data = await state.get_data()
    app_id = data.get("chat_app_id")
    partner_id = data.get("chat_partner_id")
    
    if not app_id or not partner_id:
        await message.answer("Ошибка чата. Начните заново.")
        await state.clear()
        return
    
    # Сохраняем сообщение
    await db.add_message(app_id, message.from_user.id, partner_id, message.text)
    
    # Отправляем партнеру
    try:
        sender = await db.get_username(message.from_user.id)
        await bot.send_message(
            partner_id,
            f"💬 Сообщение по заявке #{app_id} от @{sender}:\n\n{message.text}"
        )
        await message.answer("✅ Отправлено")
    except Exception as e:
        await message.answer(f"Не удалось отправить: {e}")
