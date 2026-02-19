from __future__ import annotations
import datetime as dt
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from bot.keyboards import main_menu, banks_kb, countries_kb, subscribe_kb, i_paid_kb, webapp_button
from bot.states import UserFlow
from bot.utils import gen_payment_code
from bot.notifications import NotificationManager

router = Router()


async def safe_answer(call: CallbackQuery):
    """Безопасный ответ на callback query"""
    try:
        await call.answer()
    except TelegramBadRequest:
        pass


async def ensure_username(message: Message) -> bool:
    if message.from_user and message.from_user.username:
        return True
    await message.answer("❗️ Установите @username в настройках Telegram.")
    return False


async def is_subscribed(bot, user_id: int, config, db) -> bool:
    channel_id = await db.get_setting("channel_id") or getattr(config, "channel_id", None)
    if not channel_id:
        return True
    try:
        member = await bot.get_chat_member(channel_id, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        return False


async def ensure_subscribed(message: Message, bot, config, db) -> bool:
    if await is_subscribed(bot, message.from_user.id, config, db):
        return True
    channel_url = await db.get_setting("channel_url") or getattr(config, "channel_url", "https://t.me/your_channel")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться", url=channel_url)],
        [InlineKeyboardButton(text="✅ Проверить", callback_data="check_sub")],
    ])
    await message.answer("❗️ Подпишитесь на канал:", reply_markup=kb)
    return False


@router.message(F.text.in_({"👥 Комьюнити", "Комьюнити"}))
async def community(message: Message, config, db):
    channel_url = await db.get_setting("channel_url") or getattr(config, "channel_url", "https://t.me/your_channel")
    team_url = await db.get_setting("team_url") or getattr(config, "team_url", "https://t.me/your_team")
    rules_url = await db.get_setting("rules_url") or getattr(config, "rules_url", channel_url)
    webapp_url = await db.get_setting("webapp_url")

    buttons = [
        [InlineKeyboardButton(text="📢 Канал", url=channel_url),
         InlineKeyboardButton(text="👨‍💻 Команда", url=team_url)],
        [InlineKeyboardButton(text="📜 Правила", url=rules_url)],
    ]

    if webapp_url and webapp_url.startswith("https://"):
        buttons.insert(0, [InlineKeyboardButton(text="🌐 Mini App", web_app=WebAppInfo(url=webapp_url))])

    await message.answer("👥 Комьюнити", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.message(F.text.in_({"🤝 Работать с нами", "Работать с нами"}))
async def work_with_us(message: Message, config, db):
    text = (
        "🤝 Работать с нами\n\n"
        "✅ Сделка в гаранте от $500\n"
        "🔥 Активное участие\n"
        "📌 Постоянный поток\n"
        "🤝 Уважение\n"
        "🧠 Ответственность\n\n"
        "💰 15% за реквизиты\n"
        "💰 25% за ФОП"
    )

    # Получаем support текст или используем дефолтный
    support_text_raw = config.support_text
    if "@" in support_text_raw:
        support_contact = support_text_raw.replace("Напишите в поддержку: ", "").replace("@", "").strip()
    else:
        support_contact = "nightlab_support"  # fallback

    # Создаем клавиатуру с кнопкой связи с админом
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📞 Написать админу", url=f"https://t.me/{support_contact}")]
    ])

    await message.answer(text, reply_markup=kb)


@router.message(F.text == "/start")
async def start(message: Message, state: FSMContext, db, config):
    await state.clear()

    # Проверяем реферальный код
    args = message.text.split()[1] if len(message.text.split()) > 1 else None
    if args and args.startswith("REF"):
        referrer_code = args
        referrer = await db.get_user_by_referral_code(referrer_code)
        if referrer and referrer["tg_id"] != message.from_user.id:
            await db.add_referral(referrer["tg_id"], message.from_user.id)
            # Отправляем уведомление рефереру
            from bot.notifications import NotificationManager
            notif = NotificationManager(message.bot, db)
            await notif.notify_new_referral(
                referrer["tg_id"],
                message.from_user.username or f"user_{message.from_user.id}"
            )

    if not await ensure_username(message):
        return

    first_time = not await db.user_exists(message.from_user.id)
    await db.upsert_user(message.from_user.id, message.from_user.username)
    await db.log(message.from_user.id, "START", message.from_user.username)

    if first_time:
        welcome_photo = await db.get_setting("photo_welcome")
        if welcome_photo:
            try:
                await message.answer_photo(welcome_photo, caption="👋 Добро пожаловать в NightLab!")
            except:
                await message.answer("👋 Добро пожаловать!")
        else:
            await message.answer("👋 Добро пожаловать!")

    if not await ensure_subscribed(message, message.bot, config, db):
        return

    await message.answer("Выберите действие:", reply_markup=await main_menu(db))


@router.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery, bot, config, db):
    await safe_answer(call)
    ok = await is_subscribed(bot, call.from_user.id, config, db)
    if not ok:
        channel_url = await db.get_setting("channel_url") or getattr(config, "channel_url", "https://t.me/your_channel")
        await call.message.answer("Подпишитесь:", reply_markup=subscribe_kb(channel_url))
        return
    await call.message.answer("✅ Подписка подтверждена!", reply_markup=await main_menu(db))


@router.message(F.text.in_({"🆘 Поддержка", "Поддержка"}))
async def support(message: Message, config, db):
    if not await ensure_subscribed(message, message.bot, config, db):
        return
    await message.answer(config.support_text)


# === Flow с фото ===
@router.message(F.text.in_({"💳 Получить реквизиты"}))
async def get_requisites(message: Message, state: FSMContext, db, config):
    if not await ensure_username(message):
        return
    if not await ensure_subscribed(message, message.bot, config, db):
        return

    countries = await db.list_countries(active_only=True)
    if not countries:
        await message.answer("Нет доступных стран.")
        return

    await state.set_state(UserFlow.choosing_country)

    msg = await message.answer(
        "🌍 Шаг 1/3: Выберите страну",
        reply_markup=countries_kb(countries)
    )
    await state.update_data(main_message_id=msg.message_id, chat_id=msg.chat.id)


@router.callback_query(UserFlow.choosing_country, F.data.startswith("country:"))
async def country_chosen(call: CallbackQuery, state: FSMContext, db):
    await safe_answer(call)
    country_id = int(call.data.split(":")[1])
    country = await db.get_country(country_id)

    if not country or not country["is_active"]:
        await call.answer("Страна недоступна", show_alert=True)
        return

    await state.update_data(country_id=country_id, country_name=country["name"])
    banks = await db.list_banks_by_country(country_id, active_only=True)

    if not banks:
        try:
            await call.message.edit_text(
                f"❌ В {country['name']} нет банков",
                reply_markup=None
            )
        except TelegramBadRequest:
            await call.message.answer(f"❌ В {country['name']} нет банков")
        await state.clear()
        return

    await state.set_state(UserFlow.choosing_bank)
    try:
        await call.message.edit_text(
            f"🌍 {country['name']}\n\n🏦 Шаг 2/3: Выберите банк",
            reply_markup=banks_kb(banks)
        )
    except TelegramBadRequest:
        await call.message.answer(
            f"🌍 {country['name']}\n\n🏦 Шаг 2/3: Выберите банк",
            reply_markup=banks_kb(banks)
        )


@router.callback_query(UserFlow.choosing_bank, F.data.startswith("bank:"))
async def bank_chosen(call: CallbackQuery, state: FSMContext, db):
    await safe_answer(call)
    bank_id = int(call.data.split(":")[1])
    bank = await db.get_bank(bank_id)

    if not bank or not bank["is_active"]:
        await call.answer("Банк недоступен", show_alert=True)
        return

    await state.update_data(bank_id=bank_id, bank_name=bank['bank_name'])
    await state.set_state(UserFlow.entering_amount)

    requisites = bank.get("requisites_text", "").strip()
    has_requisites = requisites and requisites != "Реквизиты не заданы. Обновите в /admin." and len(requisites) > 5
    status = "✅ Автовыдача" if has_requisites else "⏳ Оператор"

    try:
        await call.message.edit_text(
            f"🏦 {bank['bank_name']}\n"
            f"{status}\n\n"
            f"💰 Шаг 3/3: Введите сумму:",
            reply_markup=None
        )
    except TelegramBadRequest:
        await call.message.answer(
            f"🏦 {bank['bank_name']}\n"
            f"{status}\n\n"
            f"💰 Шаг 3/3: Введите сумму:"
        )


@router.message(UserFlow.entering_amount)
async def amount_entered(message: Message, state: FSMContext, db, bot, config, logger):
    if not await ensure_username(message):
        return

    raw = (message.text or "").replace(",", ".").strip()
    try:
        amount = float(raw)
        if amount <= 0:
            raise ValueError()
    except ValueError:
        await message.delete()
        return

    data = await state.get_data()
    bank_id = int(data["bank_id"])
    country_name = data.get("country_name", "Unknown")
    main_msg_id = data.get('main_message_id')
    chat_id = data.get('chat_id')

    bank = await db.get_bank(bank_id)
    if not bank:
        await message.delete()
        return

    await message.delete()

    # Генерируем код платежа
    import random
    import string
    payment_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    requisites = bank.get("requisites_text", "").strip()
    has_requisites = requisites and len(requisites) > 5 and "не заданы" not in requisites

    if has_requisites:
        # АВТОВЫДАЧА
        app_id = await db.create_application(message.from_user.id, bank_id, amount, payment_code)
        await db.set_requisites_and_start_timer(app_id, requisites, ttl_minutes=20)
        await db.set_app_status(app_id, "WAITING_PAYMENT")

        # Отправляем push-уведомление
        from bot.notifications import NotificationManager
        notif = NotificationManager(bot, db)
        expires_at = (dt.datetime.utcnow() + dt.timedelta(minutes=20)).isoformat() + "Z"
        await notif.notify_requisites_sent(
            app_id, message.from_user.id, bank['bank_name'],
            amount, requisites, expires_at
        )

        # Проверяем есть ли фото для реквизитов
        req_photo = await db.get_setting("photo_requisites")

        text = (
            f"✅ Заявка #{app_id}\n\n"
            f"🏦 {bank['bank_name']} | 💰 {amount:.2f} грн\n"
            f"🔐 {payment_code}\n\n"
            f"Реквизиты:\n{requisites}\n\n"
            f"⏳ 20 минут на оплату"
        )

        if main_msg_id:
            try:
                if req_photo:
                    await bot.delete_message(chat_id, main_msg_id)
                    await bot.send_photo(chat_id, req_photo, caption=text,
                                         reply_markup=i_paid_kb(app_id))
                else:
                    await bot.edit_message_text(
                        chat_id=chat_id, message_id=main_msg_id,
                        text=text, reply_markup=i_paid_kb(app_id)
                    )
            except Exception as e:
                logger.error(f"Error sending auto-requisites: {e}")
                await message.answer(text, reply_markup=i_paid_kb(app_id))
        else:
            if req_photo:
                await message.answer_photo(req_photo, caption=text,
                                           reply_markup=i_paid_kb(app_id))
            else:
                await message.answer(text, reply_markup=i_paid_kb(app_id))

    else:
        # МЕРЧАНТАМ
        app_id = await db.create_application(message.from_user.id, bank_id, amount, payment_code)

        # Отправляем в чат мерчантов
        merchant_chat_id = await db.get_setting("merchant_chat_id")
        if not merchant_chat_id and config.merchant_chat_id:
            merchant_chat_id = config.merchant_chat_id

        if merchant_chat_id:
            try:
                # Конвертируем в int если нужно
                if isinstance(merchant_chat_id, str):
                    merchant_chat_id = int(merchant_chat_id)

                from bot.keyboards import merchant_take_kb
                
                merch_text = (
                    f"🆕 Новая заявка\n"
                    f"ID: #{app_id}\n"
                    f"Банк: 🏦 {bank['bank_name']}\n"
                    f"Сумма: {amount:.2f} грн\n"
                    f"Код: {payment_code}\n"
                    f"От: @{message.from_user.username} (id {message.from_user.id})\n\n"
                    f"Нажмите «Взять заявку», затем выдайте реквизиты."
                )
                
                await bot.send_message(
                    merchant_chat_id,
                    merch_text,
                    reply_markup=merchant_take_kb(app_id)
                )
                logger.info(f"Sent app #{app_id} to merchant chat {merchant_chat_id}")
                
            except Exception as e:
                logger.error(f"Failed to send to merchant chat: {e}")
                await message.answer("⚠️ Заявка создана, но не удалось отправить мерчантам. Обратитесь в поддержку.")
        else:
            logger.warning("merchant_chat_id not configured")
            await message.answer("⚠️ Заявка создана, но чат мерчантов не настроен. Обратитесь в поддержку.")

        # Показываем пользователю ожидание
        wait_photo = await db.get_setting("photo_waiting")
        text = f"⏳ Заявка #{app_id} отправлена оператору..."

        if main_msg_id:
            try:
                if wait_photo:
                    await bot.delete_message(chat_id, main_msg_id)
                    await bot.send_photo(chat_id, wait_photo, caption=text)
                else:
                    await bot.edit_message_text(
                        chat_id=chat_id, message_id=main_msg_id,
                        text=text, reply_markup=None
                    )
            except Exception as e:
                logger.error(f"Error showing waiting: {e}")
                await message.answer(text)
        else:
            if wait_photo:
                await message.answer_photo(wait_photo, caption=text)
            else:
                await message.answer(text)

    await state.clear()

@router.message(F.text == "/chatid")
async def chatid(message: Message):
    await message.answer(f"chat_id: {message.chat.id}")


@router.message(F.text == "/health")
async def health(message: Message, db):
    cols = getattr(db, "_app_cols", None)
    await message.answer(f"OK v5.0\napp_cols={sorted(list(cols)) if cols else 'unknown'}")


# === WebApp Data Handler ===
@router.message(lambda m: m.web_app_data)
async def webapp_data_handler(message: Message, db, config, bot, logger):
    """Обработка данных от WebApp - связь WebApp ↔ Бот"""
    try:
        import json
        data = json.loads(message.web_app_data.data)
        action = data.get('action')

        if action == 'new_app_merchant':
            # WebApp создал заявку без автовыдачи, нужно отправить в чат мерчантов
            app_id = data.get('app_id')
            bank_name = data.get('bank_name', 'Unknown')
            amount = data.get('amount', 0)
            country_name = data.get('country_name', 'Unknown')

            # Получаем детали заявки из БД
            app = await db.get_application(app_id)
            if not app:
                await message.answer("❌ Ошибка: заявка не найдена")
                return

            # Отправляем в чат мерчантов
            merchant_chat_id = await db.get_setting("merchant_chat_id")
            if not merchant_chat_id and config.merchant_chat_id:
                merchant_chat_id = config.merchant_chat_id

            if merchant_chat_id:
                try:
                    if isinstance(merchant_chat_id, str) and merchant_chat_id.lstrip("-").isdigit():
                        merchant_chat_id = int(merchant_chat_id)

                    from bot.keyboards import merchant_take_kb

                    merch_text = (
                        f"🆕 Новая заявка (через WebApp)\n"
                        f"ID: #{app_id}\n"
                        f"Банк: 🏦 {bank_name}\n"
                        f"Сумма: {float(amount):.2f} грн\n"
                        f"Код: {app['payment_code']}\n"
                        f"От: @{message.from_user.username} (id {message.from_user.id})\n\n"
                        f"Нажмите «Взять заявку», затем выдайте реквизиты."
                    )

                    await bot.send_message(
                        merchant_chat_id,
                        merch_text,
                        reply_markup=merchant_take_kb(app_id)
                    )
                    logger.info(f"WebApp app #{app_id} sent to merchant chat {merchant_chat_id}")
                    await message.answer(f"✅ Заявка #{app_id} отправлена оператору!")

                except Exception as e:
                    logger.error(f"Failed to send WebApp app to merchants: {e}")
                    await message.answer(f"⚠️ Заявка #{app_id} создана, но не удалось отправить операторам.")
            else:
                logger.warning("merchant_chat_id not configured")
                await message.answer(f"⚠️ Чат операторов не настроен. Обратитесь в поддержку.")

        elif action == 'app_created':
            await message.answer(
                f"✅ Заявка #{data.get('app_id')} создана через WebApp!\n\n"
                f"Отслеживайте статус в разделе '📄 Мои заявки'",
                reply_markup=await main_menu(db)
            )

        elif action == 'refresh_data':
            # Принудительное обновление данных
            await message.answer("🔄 Данные обновлены!", reply_markup=await main_menu(db))

        elif action == 'open_support':
            await message.answer(config.support_text)

        else:
            await message.answer(f"Получены данные от WebApp: {data}")

    except Exception as e:
        logger.error(f"WebApp data error: {e}")
        await message.answer(f"Ошибка обработки данных WebApp: {e}")


@router.message(F.text == "🌐 Личный кабинет")
async def open_webapp(message: Message, db):
    """Открыть WebApp"""
    webapp_url = await db.get_setting("webapp_url")
    if webapp_url and webapp_url.startswith("https://"):
        await message.answer(
            "🌐 Личный кабинет NightLab\n\n"
            "Здесь вы можете:\n"
            "• Создавать заявки\n"
            "• Смотреть историю\n"
            "• Управлять профилем\n"
            "• Получать уведомления",
            reply_markup=webapp_button(webapp_url)
        )
    else:
        await message.answer("WebApp временно недоступен. Обратитесь к администратору.")
