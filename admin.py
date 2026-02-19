from __future__ import annotations
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from bot.states import AdminFlow
from bot.keyboards import (
    admin_menu_kb, admin_banks_kb, admin_countries_kb, admin_roles_kb,
    admin_photos_kb, admin_bank_item_kb, admin_country_item_kb,
    admin_choose_role_kb, admin_settings_kb, confirm_broadcast_kb
)

router = Router()

def is_admin(user_id: int, config) -> bool:
    return user_id in config.admin_ids

async def safe_answer(call: CallbackQuery):
    """Безопасный ответ на callback query"""
    try:
        await call.answer()
    except TelegramBadRequest:
        pass  # Query слишком старый, игнорируем

@router.message(F.text == "/admin")
async def admin_cmd(message: Message, config, db):
    if not is_admin(message.from_user.id, config):
        await message.answer("Нет доступа.")
        return
    await message.answer("Админ-панель:", reply_markup=admin_menu_kb())

@router.callback_query(F.data == "admin:back")
async def admin_back(call: CallbackQuery):
    await safe_answer(call)
    try:
        await call.message.edit_text("Админ-панель:", reply_markup=admin_menu_kb())
    except TelegramBadRequest:
        await call.message.answer("Админ-панель:", reply_markup=admin_menu_kb())

# === Banks ===
@router.callback_query(F.data == "admin:banks")
async def admin_banks(call: CallbackQuery):
    await safe_answer(call)
    try:
        await call.message.edit_text("Управление банками:", reply_markup=admin_banks_kb())
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "admin:add_bank")
async def admin_add_bank(call: CallbackQuery, state: FSMContext):
    await safe_answer(call)
    await state.set_state(AdminFlow.entering_bank_name)
    await call.message.answer("Введите название банка:")

@router.message(AdminFlow.entering_bank_name)
async def admin_bank_name_entered(message: Message, state: FSMContext):
    await state.update_data(bank_name=message.text)
    await state.set_state(AdminFlow.entering_requisites_text)
    await message.answer("Введите реквизиты (текстом):")

@router.message(AdminFlow.entering_requisites_text)
async def admin_requisites_entered(message: Message, state: FSMContext, db):
    data = await state.get_data()
    bank_name = data.get("bank_name")
    requisites = message.text
    
    await db.upsert_bank(bank_name, requisites)
    await message.answer(f"✅ Банк '{bank_name}' добавлен/обновлен!")
    await state.clear()

@router.callback_query(F.data == "admin:list_banks")
async def admin_list_banks(call: CallbackQuery, db):
    await safe_answer(call)
    banks = await db.list_banks(active_only=False)
    if not banks:
        await call.message.answer("Нет банков.")
        return
    
    text = "📋 Список банков:\n\n"
    for bank_id, bank_name, is_active in banks:
        status = "✅" if is_active else "🚫"
        text += f"{status} {bank_name} (ID: {bank_id})\n"
    
    await call.message.answer(text)

# === Countries ===
@router.callback_query(F.data == "admin:countries")
async def admin_countries(call: CallbackQuery):
    await safe_answer(call)
    try:
        await call.message.edit_text("Управление странами:", reply_markup=admin_countries_kb())
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "admin:add_country")
async def admin_add_country(call: CallbackQuery, state: FSMContext):
    await safe_answer(call)
    await state.set_state(AdminFlow.entering_country_name)
    await call.message.answer("Введите название страны:")

@router.message(AdminFlow.entering_country_name)
async def admin_country_name_entered(message: Message, state: FSMContext, db):
    await db.upsert_country(message.text)
    await message.answer(f"✅ Страна '{message.text}' добавлена!")
    await state.clear()

@router.callback_query(F.data == "admin:list_countries")
async def admin_list_countries(call: CallbackQuery, db):
    await safe_answer(call)
    countries = await db.list_countries(active_only=False)
    if not countries:
        await call.message.answer("Нет стран.")
        return
    
    text = "📋 Список стран:\n\n"
    for country_id, name, is_active in countries:
        status = "✅" if is_active else "🚫"
        text += f"{status} {name} (ID: {country_id})\n"
    
    await call.message.answer(text)

# === Roles ===
@router.callback_query(F.data == "admin:roles")
async def admin_roles(call: CallbackQuery):
    await safe_answer(call)
    try:
        await call.message.edit_text("Управление ролями:", reply_markup=admin_roles_kb())
    except TelegramBadRequest:
        pass

@router.callback_query(F.data == "admin:set_role")
async def admin_set_role(call: CallbackQuery, state: FSMContext):
    await safe_answer(call)
    await state.set_state(AdminFlow.entering_user_id)
    await call.message.answer("Введите Telegram ID пользователя:")

@router.message(AdminFlow.entering_user_id)
async def admin_user_id_entered(message: Message, state: FSMContext, db):
    try:
        tg_id = int(message.text)
        user = await db.get_user(tg_id)
        if not user:
            await message.answer("Пользователь не найден.")
            await state.clear()
            return
        
        await state.update_data(target_user_id=tg_id)
        await message.answer(
            f"Пользователь: @{user['username']}\n"
            f"Текущая роль: {user['role']}\n\n"
            f"Выберите новую роль:",
            reply_markup=admin_choose_role_kb(tg_id)
        )
        await state.clear()
    except ValueError:
        await message.answer("Введите числовой ID.")

@router.callback_query(F.data.startswith("admin:role:"))
async def admin_role_selected(call: CallbackQuery, db):
    await safe_answer(call)
    parts = call.data.split(":")
    tg_id = int(parts[2])
    role = parts[3]
    
    await db.set_user_role(tg_id, role)
    await call.message.answer(f"✅ Роль пользователя {tg_id} изменена на {role}")

# === Settings ===
@router.callback_query(F.data == "admin:settings")
async def admin_settings(call: CallbackQuery):
    await safe_answer(call)
    try:
        await call.message.edit_text("Настройки:", reply_markup=admin_settings_kb())
    except TelegramBadRequest:
        pass

@router.callback_query(F.data.startswith("admin:setting:"))
async def admin_setting_selected(call: CallbackQuery, state: FSMContext):
    await safe_answer(call)
    setting_key = call.data.split(":")[2]
    await state.set_state(AdminFlow.entering_setting_value)
    await state.update_data(setting_key=setting_key)
    
    setting_names = {
        "channel_url": "URL канала",
        "team_url": "URL команды",
        "rules_url": "URL правил",
        "webapp_url": "URL WebApp",
        "channel_id": "ID канала",
        "merchant_chat_id": "ID чата мерчантов"
    }
    
    await call.message.answer(f"Введите значение для {setting_names.get(setting_key, setting_key)}:")

@router.message(AdminFlow.entering_setting_value)
async def admin_setting_value_entered(message: Message, state: FSMContext, db):
    data = await state.get_data()
    setting_key = data.get("setting_key")
    value = message.text
    
    await db.set_setting(setting_key, value)
    await message.answer(f"✅ Настройка '{setting_key}' обновлена!")
    await state.clear()

# === Broadcast ===
@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast(call: CallbackQuery, state: FSMContext):
    await safe_answer(call)
    await state.set_state(AdminFlow.entering_broadcast)
    await call.message.answer("Введите сообщение для рассылки:")

@router.message(AdminFlow.entering_broadcast)
async def admin_broadcast_message(message: Message, state: FSMContext):
    await state.update_data(broadcast_message=message.text)
    await message.answer(
        f"Сообщение для рассылки:\n\n{message.text}\n\n"
        f"Подтвердите отправку:",
        reply_markup=confirm_broadcast_kb()
    )

@router.callback_query(F.data == "admin:broadcast_confirm")
async def admin_broadcast_confirm(call: CallbackQuery, state: FSMContext, db, bot):
    await safe_answer(call)
    data = await state.get_data()
    message_text = data.get("broadcast_message")
    
    users = await db.get_all_users()
    sent = 0
    failed = 0
    
    for user_id in users:
        try:
            await bot.send_message(user_id, message_text)
            sent += 1
        except Exception:
            failed += 1
    
    await call.message.answer(f"✅ Рассылка завершена!\nОтправлено: {sent}\nНе удалось: {failed}")
    await state.clear()

# === Photos ===
@router.callback_query(F.data == "admin:photos")
async def admin_photos(call: CallbackQuery):
    await safe_answer(call)
    try:
        await call.message.edit_text("Управление фото:", reply_markup=admin_photos_kb())
    except TelegramBadRequest:
        pass

@router.callback_query(F.data.startswith("admin:photo:"))
async def admin_photo_selected(call: CallbackQuery, state: FSMContext):
    await safe_answer(call)
    photo_type = call.data.split(":")[2]
    await state.set_state(AdminFlow.entering_photo)
    await state.update_data(photo_type=photo_type)
    
    photo_names = {
        "welcome": "приветствия",
        "requisites": "реквизитов",
        "waiting": "ожидания",
        "success": "успеха"
    }
    
    await call.message.answer(f"Отправьте фото для {photo_names.get(photo_type, photo_type)}:")

@router.message(AdminFlow.entering_photo)
async def admin_photo_received(message: Message, state: FSMContext, db):
    if not message.photo:
        await message.answer("Пожалуйста, отправьте фото.")
        return
    
    data = await state.get_data()
    photo_type = data.get("photo_type")
    file_id = message.photo[-1].file_id
    
    await db.set_setting(f"photo_{photo_type}", file_id)
    await message.answer(f"✅ Фото для '{photo_type}' сохранено!")
    await state.clear()
