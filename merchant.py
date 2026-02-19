from __future__ import annotations
import datetime as dt
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from bot.states import MerchantFlow
from bot.keyboards import merchant_send_mode_kb, i_paid_kb, merchant_take_kb, merchant_taken_kb
from bot.notifications import NotificationManager

router = Router()

def can_merchant(role: str, user_id: int, config) -> bool:
    return (role in ("MERCHANT", "ADMIN")) or (user_id in config.admin_ids)

async def safe_answer(call: CallbackQuery):
    """Безопасный ответ на callback query"""
    try:
        await call.answer()
    except TelegramBadRequest:
        pass

@router.callback_query(F.data.startswith("take:"))
async def take_app(call: CallbackQuery, state: FSMContext, db, config):
    app_id = int(call.data.split(":")[1])
    role = await db.get_user_role(call.from_user.id)
    if not can_merchant(role, call.from_user.id, config):
        try:
            await call.answer("Нет прав", show_alert=True)
        except TelegramBadRequest:
            pass
        return

    app = await db.get_application(app_id)
    if not app:
        try:
            await call.answer("Заявка не найдена", show_alert=True)
        except TelegramBadRequest:
            pass
        return
    if app["status"] != "WAITING_MERCHANT":
        try:
            await call.answer(f"Уже взята/неактуальна (статус {app['status']})", show_alert=True)
        except TelegramBadRequest:
            pass
        return

    ok = await db.assign_merchant(app_id, call.from_user.id)
    if not ok:
        try:
            await call.answer("Не удалось взять (уже взяли)", show_alert=True)
        except TelegramBadRequest:
            pass
        return

    await db.log(call.from_user.id, "APP_TAKEN", f"app_id={app_id}")

    try:
        await call.message.edit_text(call.message.text + f"\n\n✅ Взял: @{call.from_user.username} (id {call.from_user.id})")
        await call.message.edit_reply_markup(reply_markup=merchant_taken_kb(app_id))
    except TelegramBadRequest:
        pass

    try:
        await call.answer("Заявка закреплена за вами")
    except TelegramBadRequest:
        pass

    await state.clear()
    await state.set_state(MerchantFlow.choosing_send_mode)
    await state.update_data(app_id=app_id)
    try:
        await call.bot.send_message(
            call.from_user.id,
            f"Заявка #{app_id} у вас. Как отправим реквизиты?",
            reply_markup=merchant_send_mode_kb(app_id),
        )
    except Exception:
        try:
            await call.message.answer("⚠️ Не могу написать в ЛС. Напишите боту /start в личке и повторите.")
        except Exception:
            pass

@router.callback_query(F.data.startswith("release:"))
async def release_app(call: CallbackQuery, db, config):
    await safe_answer(call)
    app_id = int(call.data.split(":")[1])
    role = await db.get_user_role(call.from_user.id)
    if not can_merchant(role, call.from_user.id, config):
        try:
            await call.answer("Нет прав", show_alert=True)
        except TelegramBadRequest:
            pass
        return

    app = await db.get_application(app_id)
    if not app:
        await call.message.answer("Заявка не найдена.")
        return

    if role != "ADMIN" and call.from_user.id not in config.admin_ids:
        if app.get("assigned_merchant_tg_id") != call.from_user.id:
            try:
                await call.answer("Заявка не закреплена за вами", show_alert=True)
            except TelegramBadRequest:
                pass
            return

    if app["status"] != "MERCHANT_TAKEN":
        try:
            await call.answer(f"Нельзя вернуть (статус {app['status']})", show_alert=True)
        except TelegramBadRequest:
            pass
        return

    ok = await db.unassign_merchant(app_id, None if (role=="ADMIN" or call.from_user.id in config.admin_ids) else call.from_user.id)
    if not ok:
        try:
            await call.answer("Не удалось вернуть (возможно, уже изменили)", show_alert=True)
        except TelegramBadRequest:
            pass
        return

    bank = await db.get_bank(app["bank_id"]) if app.get("bank_id") else None
    bank_name = bank["bank_name"] if bank else str(app.get("bank_id") or "-")
    from_username = await db.get_username(app["user_tg_id"])
    from_label = f"@{from_username}" if from_username else str(app["user_tg_id"])

    text = (
        f"🆕 Новая заявка\n"
        f"ID: #{app_id}\n"
        f"Банк: {bank_name}\n"
        f"Сумма: {app['amount_uah']:.2f} грн\n"
        f"Код: {app['payment_code']}\n"
        f"От: {from_label} (id {app['user_tg_id']})\n\n"
        f"Нажмите «Взять заявку», затем выдайте реквизиты."
    )
    try:
        await call.message.edit_text(text)
        await call.message.edit_reply_markup(reply_markup=merchant_take_kb(app_id))
    except TelegramBadRequest:
        await call.bot.send_message(config.merchant_chat_id, text, reply_markup=merchant_take_kb(app_id))

    await db.log(call.from_user.id, "APP_RELEASED", f"app_id={app_id}")

@router.callback_query(F.data.startswith("send_saved:"))
async def send_saved(call: CallbackQuery, state: FSMContext, db, bot):
    await safe_answer(call)
    app_id = int(call.data.split(":")[1])
    app = await db.get_application(app_id)
    if not app:
        await call.message.answer("Заявка не найдена.")
        await state.clear()
        return
    bank = await db.get_bank(app["bank_id"])
    if not bank:
        await call.message.answer("Банк не найден.")
        await state.clear()
        return
    if app["status"] != "MERCHANT_TAKEN":
        await call.message.answer(f"Нельзя выдать реквизиты (статус {app['status']}).")
        await state.clear()
        return

    ok = await db.set_requisites_and_start_timer(app_id, bank["requisites_text"], ttl_minutes=20)
    if not ok:
        await call.message.answer("Не удалось обновить заявку (возможно, статус изменился).")
        await state.clear()
        return

    # Отправляем push-уведомление пользователю
    notif = NotificationManager(bot, db)
    expires_at = (dt.datetime.utcnow() + dt.timedelta(minutes=20)).isoformat() + "Z"
    await notif.notify_requisites_sent(
        app_id, 
        app["user_tg_id"], 
        bank['bank_name'], 
        app['amount_uah'], 
        bank["requisites_text"], 
        expires_at
    )

    text = (
        f"✅ Реквизиты для оплаты\n\n"
        f"🏦 Банк: {bank['bank_name']}\n"
        f"💰 Сумма: {app['amount_uah']:.2f} грн\n"
        f"🔐 Код платежа: {app['payment_code']}\n\n"
        f"Реквизиты:\n{bank['requisites_text']}\n\n"
        f"После оплаты нажмите «Я оплатил» (у вас есть 20 минут)."
    )
    try:
        await bot.send_message(app["user_tg_id"], text, reply_markup=i_paid_kb(app_id))
        await call.message.answer("Готово! Сохранённые реквизиты отправлены пользователю.")
    except Exception:
        await call.message.answer("Не смог отправить пользователю (возможно, он заблокировал бота).")
    await state.clear()

@router.callback_query(F.data.startswith("send_new:"))
async def send_new(call: CallbackQuery, state: FSMContext):
    await safe_answer(call)
    app_id = int(call.data.split(":")[1])
    await state.clear()
    await state.set_state(MerchantFlow.entering_requisites)
    await state.update_data(app_id=app_id)
    await call.message.answer(
        "Пришлите одним сообщением новые реквизиты (текст).\n"
        "Я их отправлю пользователю и сохраню как шаблон банка."
    )

@router.message(MerchantFlow.entering_requisites)
async def merchant_new_requisites(message: Message, state: FSMContext, db, bot):
    data = await state.get_data()
    app_id = int(data.get("app_id", 0))
    app = await db.get_application(app_id)
    if not app:
        await message.answer("Заявка не найдена/устарела.")
        await state.clear()
        return
    if app["assigned_merchant_tg_id"] != message.from_user.id:
        await message.answer("Эта заявка не закреплена за вами.")
        await state.clear()
        return
    if app["status"] != "MERCHANT_TAKEN":
        await message.answer(f"Нельзя выдать реквизиты (статус {app['status']}).")
        await state.clear()
        return

    requisites = (message.text or "").strip()
    if len(requisites) < 5:
        await message.answer("Слишком коротко. Пришлите реквизиты одним сообщением (текстом).")
        return

    ok = await db.set_requisites_and_start_timer(app_id, requisites, ttl_minutes=20)
    if not ok:
        await message.answer("Не удалось обновить заявку (возможно, статус изменился).")
        await state.clear()
        return

    bank = await db.get_bank(app["bank_id"])
    if bank:
        await db.upsert_bank(bank["bank_name"], requisites)

    # Отправляем push-уведомление пользователю
    notif = NotificationManager(bot, db)
    expires_at = (dt.datetime.utcnow() + dt.timedelta(minutes=20)).isoformat() + "Z"
    await notif.notify_requisites_sent(
        app_id, 
        app["user_tg_id"], 
        bank['bank_name'] if bank else 'Unknown', 
        app['amount_uah'], 
        requisites, 
        expires_at
    )

    text = (
        f"✅ Реквизиты для оплаты\n\n"
        f"🏦 Банк: {bank['bank_name'] if bank else app['bank_id']}\n"
        f"💰 Сумма: {app['amount_uah']:.2f} грн\n"
        f"🔐 Код платежа: {app['payment_code']}\n\n"
        f"Реквизиты:\n{requisites}\n\n"
        f"После оплаты нажмите «Я оплатил» (у вас есть 20 минут)."
    )
    try:
        await bot.send_message(app["user_tg_id"], text, reply_markup=i_paid_kb(app_id))
        await message.answer("Готово! Реквизиты отправлены пользователю и сохранены для банка.")
    except Exception:
        await message.answer("Не смог отправить пользователю (возможно, он заблокировал бота).")

    await state.clear()
