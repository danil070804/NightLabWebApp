from __future__ import annotations
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from bot.keyboards import receipt_kb, check_kb
from bot.notifications import NotificationManager
from bot.states import AdminFlow

router = Router()

async def safe_answer(call: CallbackQuery):
    """Безопасный ответ на callback query"""
    try:
        await call.answer()
    except TelegramBadRequest:
        pass

@router.callback_query(F.data.startswith("cancel:"))
async def cancel_app(call: CallbackQuery, db):
    await safe_answer(call)
    app_id = int(call.data.split(":")[1])
    app = await db.get_application(app_id)
    if not app or app["user_tg_id"] != call.from_user.id:
        return
    if app["status"] in ("CONFIRMED", "REJECTED", "EXPIRED"):
        await call.message.answer("Эта заявка уже закрыта.")
        return
    await db.set_app_status(app_id, "REJECTED")
    await db.log(call.from_user.id, "APP_CANCELED", f"app_id={app_id}")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await call.message.answer(f"Заявка #{app_id} отменена.")

@router.callback_query(F.data.startswith("paid:"))
async def paid(call: CallbackQuery, db):
    await safe_answer(call)
    app_id = int(call.data.split(":")[1])
    app = await db.get_application(app_id)
    if not app or app["user_tg_id"] != call.from_user.id:
        return

    if app["status"] == "EXPIRED":
        await call.message.answer("⏳ Время ожидания истекло (20 минут). Создайте новую заявку.")
        return
    if app["status"] != "WAITING_PAYMENT":
        await call.message.answer(f"Текущий статус: {app['status']}")
        return

    await db.set_app_status(app_id, "WAITING_RECEIPT")
    await db.log(call.from_user.id, "USER_PAID", f"app_id={app_id}")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await call.message.answer("Хотите прикрепить чек/скрин оплаты?", reply_markup=receipt_kb(app_id))

@router.callback_query(F.data.startswith("skip_receipt:"))
async def skip_receipt(call: CallbackQuery, db, bot, config, logger):
    await safe_answer(call)
    app_id = int(call.data.split(":")[1])
    await _send_to_check(call, db, bot, config, logger, app_id)

@router.callback_query(F.data.startswith("receipt:"))
async def receipt_hint(call: CallbackQuery):
    await safe_answer(call)
    app_id = int(call.data.split(":")[1])
    await call.message.answer(f"Пришлите фото/документ чека одним сообщением.\nЕсли отправляете не сразу после оплаты — добавьте в подпись: #{app_id}")

@router.message(F.photo | F.document)
async def receipt_upload(message: Message, db, bot, config, logger):
    caption = (message.caption or "")
    import re
    m = re.search(r"#(\d+)", caption)
    app_id = int(m.group(1)) if m else None

    # Если ID не указан в подписи - ищем последнюю активную заявку пользователя
    if not app_id:
        rows = await db.list_user_apps(message.from_user.id, limit=20)
        logger.info(f"Looking for app for user {message.from_user.id}, found {len(rows)} apps")
        
        # Сначала ищем заявку ожидающую чек
        for app_id_cand, _bank, _amount, _code, status, _created in rows:
            if status == "WAITING_RECEIPT":
                app_id = int(app_id_cand)
                logger.info(f"Found app {app_id} with status WAITING_RECEIPT")
                break
        
        # Если не нашли - ищем заявку ожидающую оплату
        if not app_id:
            for app_id_cand, _bank, _amount, _code, status, _created in rows:
                if status == "WAITING_PAYMENT":
                    app_id = int(app_id_cand)
                    logger.info(f"Found app {app_id} with status WAITING_PAYMENT")
                    break

    if not app_id:
        await message.answer(
            "❓ Не понял, к какой заявке прикрепить чек.\n\n"
            "Отправьте чек ещё раз и добавьте в подпись: #<номер> (например #12)\n"
            "Или нажмите «Я оплатил» по нужной заявке."
        )
        return

    app = await db.get_application(app_id)
    if not app or app["user_tg_id"] != message.from_user.id:
        await message.answer("❌ Заявка не найдена.")
        return
    
    # Разрешаем прикреплять чек к заявкам в статусах WAITING_RECEIPT или WAITING_PAYMENT
    if app["status"] not in ["WAITING_RECEIPT", "WAITING_PAYMENT"]:
        await message.answer(
            f"⏳ Сейчас по заявке статус: {app['status']}\n"
            f"Чек можно прикрепить только после нажатия «Я оплатил»."
        )
        return

    # Получаем file_id
    if message.photo:
        file_id = message.photo[-1].file_id
        ftype = "photo"
    elif message.document:
        file_id = message.document.file_id
        ftype = "document"
    else:
        await message.answer("❌ Не удалось получить файл. Попробуйте ещё раз.")
        return

    logger.info(f"Saving receipt for app {app_id}: file_id={file_id}, type={ftype}")
    
    # Сохраняем чек
    await db.set_receipt(app_id, file_id, ftype)
    await db.log(message.from_user.id, "RECEIPT_UPLOADED", f"app_id={app_id};type={ftype}")
    
    # Если статус WAITING_PAYMENT - меняем на WAITING_RECEIPT
    if app["status"] == "WAITING_PAYMENT":
        await db.set_app_status(app_id, "WAITING_RECEIPT")
        logger.info(f"Changed app {app_id} status from WAITING_PAYMENT to WAITING_RECEIPT")
    
    await message.answer("✅ Чек прикреплён! Отправляю на проверку...")
    await _send_to_check(message, db, bot, config, logger, app_id)

async def _send_to_check(ctx, db, bot, config, logger, app_id: int):
    app = await db.get_application(app_id)
    if not app:
        return
    await db.set_app_status(app_id, "WAITING_CHECK")

    bank = await db.get_bank(app["bank_id"])
    uname = getattr(ctx.from_user, "username", "")
    uid = getattr(ctx.from_user, "id", "")
    notify_text = (
        f"🧾 Заявка на проверку\n"
        f"ID: #{app_id}\n"
        f"Пользователь: @{uname} (id {uid})\n"
        f"Банк: {bank['bank_name'] if bank else app['bank_id']}\n"
        f"Сумма: {app['amount_uah']:.2f} грн\n"
        f"Код: {app['payment_code']}\n"
        f"Статус: 🟡 На проверке (WAITING_CHECK)"
    )

    targets = set(config.admin_ids)
    if app.get("assigned_merchant_tg_id"):
        targets.add(int(app["assigned_merchant_tg_id"]))

    for tid in targets:
        try:
            await bot.send_message(tid, notify_text, reply_markup=check_kb(app_id))
            if app.get("receipt_file_id"):
                if app.get("receipt_file_type") == "photo":
                    await bot.send_photo(tid, app["receipt_file_id"], caption=f"Чек по заявке #{app_id}")
                else:
                    await bot.send_document(tid, app["receipt_file_id"], caption=f"Чек по заявке #{app_id}")
        except Exception as e:
            logger.warning("Failed to notify %s: %s", tid, e)

    try:
        await bot.send_message(app["user_tg_id"], "Спасибо! Оплата отправлена на проверку. Ожидайте подтверждения.")
    except Exception:
        pass

@router.callback_query(F.data.startswith("approve:"))
async def approve_payment(call: CallbackQuery, db, bot, config):
    """Подтвердить платеж (админ/мерчант)"""
    await safe_answer(call)
    
    app_id = int(call.data.split(":")[1])
    app = await db.get_application(app_id)
    
    if not app:
        await call.message.answer("Заявка не найдена.")
        return
    
    # Проверяем права
    role = await db.get_user_role(call.from_user.id)
    is_admin = role == "ADMIN" or call.from_user.id in config.admin_ids
    is_merchant = role == "MERCHANT" or app.get("assigned_merchant_tg_id") == call.from_user.id
    
    if not (is_admin or is_merchant):
        try:
            await call.answer("Нет прав для подтверждения", show_alert=True)
        except TelegramBadRequest:
            pass
        return
    
    # Обновляем статус
    await db.set_app_status(app_id, "CONFIRMED")
    await db.log(call.from_user.id, "PAYMENT_APPROVED", f"app_id={app_id}")
    
    # Отправляем уведомление пользователю
    bank = await db.get_bank(app["bank_id"])
    notif = NotificationManager(bot, db)
    await notif.notify_payment_confirmed(
        app_id,
        app["user_tg_id"],
        bank["bank_name"] if bank else "Unknown",
        app["amount_uah"]
    )
    
    # Обновляем сообщение
    try:
        await call.message.edit_text(
            call.message.text + f"\n\n✅ Подтверждено: @{call.from_user.username}",
            reply_markup=None
        )
    except TelegramBadRequest:
        pass
    
    await call.message.answer(f"✅ Заявка #{app_id} подтверждена!")

@router.callback_query(F.data.startswith("reject:"))
async def reject_payment(call: CallbackQuery, state: FSMContext, db, bot, config):
    """Отклонить платеж (админ/мерчант)"""
    await safe_answer(call)
    
    app_id = int(call.data.split(":")[1])
    app = await db.get_application(app_id)
    
    if not app:
        await call.message.answer("Заявка не найдена.")
        return
    
    # Проверяем права
    role = await db.get_user_role(call.from_user.id)
    is_admin = role == "ADMIN" or call.from_user.id in config.admin_ids
    is_merchant = role == "MERCHANT" or app.get("assigned_merchant_tg_id") == call.from_user.id
    
    if not (is_admin or is_merchant):
        try:
            await call.answer("Нет прав для отклонения", show_alert=True)
        except TelegramBadRequest:
            pass
        return
    
    # Запрашиваем причину
    await state.set_state(AdminFlow.entering_reject_reason)
    await state.update_data(reject_app_id=app_id)
    
    await call.message.answer("Введите причину отклонения:")

@router.message(AdminFlow.entering_reject_reason)
async def process_reject_reason(message: Message, state: FSMContext, db, bot, config):
    """Обработка причины отклонения"""
    data = await state.get_data()
    app_id = data.get("reject_app_id")
    reason = message.text
    
    if not app_id:
        await message.answer("Ошибка: заявка не найдена.")
        await state.clear()
        return
    
    app = await db.get_application(app_id)
    if not app:
        await message.answer("Заявка не найдена.")
        await state.clear()
        return
    
    # Обновляем статус
    await db.set_app_status(app_id, "REJECTED")
    await db.log(message.from_user.id, "PAYMENT_REJECTED", f"app_id={app_id};reason={reason}")
    
    # Отправляем уведомление пользователю
    bank = await db.get_bank(app["bank_id"])
    notif = NotificationManager(bot, db)
    await notif.notify_payment_rejected(
        app_id,
        app["user_tg_id"],
        bank["bank_name"] if bank else "Unknown",
        app["amount_uah"],
        reason
    )
    
    await message.answer(f"❌ Заявка #{app_id} отклонена.")
    await state.clear()
