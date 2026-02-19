from __future__ import annotations
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder


async def main_menu(db=None) -> ReplyKeyboardMarkup:
    """Главное меню с опциональной кнопкой WebApp"""

    keyboard = []

    # Добавляем кнопку WebApp первой (в верхнем ряду), только если есть валидный URL
    if db:
        webapp_url = await db.get_setting("webapp_url", "")
        if webapp_url and webapp_url.startswith("https://"):
            keyboard.append([KeyboardButton(text="🚀 Открыть WebApp Lab", web_app=WebAppInfo(url=webapp_url))])

    # Основные кнопки
    keyboard.extend([
        [KeyboardButton(text="💳 Получить реквизиты"), KeyboardButton(text="📄 Мои заявки")],
        [KeyboardButton(text="👥 Комьюнити"), KeyboardButton(text="🆘 Поддержка"),
         KeyboardButton(text="🤝 Работать с нами")],
    ])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
    )


def webapp_button(url: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🌐 Открыть Mini App", web_app=WebAppInfo(url=url))
    return b.as_markup()


def countries_kb(countries: list[tuple[int, str, int]]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for country_id, name, _active in countries:
        b.button(text=name, callback_data=f"country:{country_id}")
    b.adjust(2)
    return b.as_markup()


def banks_kb(banks: list[tuple[int, str, int]]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for bank_id, bank_name, _active in banks:
        b.button(text=bank_name, callback_data=f"bank:{bank_id}")
    b.adjust(2)
    return b.as_markup()


def merchant_take_kb(app_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🤝 Взять заявку", callback_data=f"take:{app_id}")
    return b.as_markup()


def merchant_send_mode_kb(app_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📤 Отправить сохранённые реквизиты", callback_data=f"send_saved:{app_id}")
    b.button(text="✍️ Ввести новые реквизиты", callback_data=f"send_new:{app_id}")
    b.adjust(1)
    return b.as_markup()


def i_paid_kb(app_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Я оплатил", callback_data=f"paid:{app_id}")
    b.button(text="✉️ Чат", callback_data=f"chat:{app_id}")
    b.button(text="❌ Отмена", callback_data=f"cancel:{app_id}")
    b.adjust(2, 1)
    return b.as_markup()


def receipt_kb(app_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📎 Прикрепить чек", callback_data=f"receipt:{app_id}")
    b.button(text="Пропустить", callback_data=f"skip_receipt:{app_id}")
    b.adjust(1)
    return b.as_markup()


def check_kb(app_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Подтвердить", callback_data=f"approve:{app_id}")
    b.button(text="❌ Отклонить", callback_data=f"reject:{app_id}")
    b.button(text="✉️ Ответить", callback_data=f"chat:{app_id}")
    b.adjust(2, 1)
    return b.as_markup()


# Admin keyboards
def admin_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🏦 Банки/реквизиты", callback_data="admin:banks")
    b.button(text="🌍 Страны", callback_data="admin:countries")
    b.button(text="👤 Роли", callback_data="admin:roles")
    b.button(text="📢 Рассылка", callback_data="admin:broadcast")
    b.button(text="⚙️ Настройки", callback_data="admin:settings")
    b.button(text="🖼 Управление фото", callback_data="admin:photos")
    b.adjust(2, 2, 2)
    return b.as_markup()


def admin_banks_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Добавить/обновить банк", callback_data="admin:add_bank")
    b.button(text="📋 Список банков", callback_data="admin:list_banks")
    b.button(text="⬅️ Назад", callback_data="admin:back")
    b.adjust(1)
    return b.as_markup()


def admin_countries_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Добавить страну", callback_data="admin:add_country")
    b.button(text="📋 Список стран", callback_data="admin:list_countries")
    b.button(text="⬅️ Назад", callback_data="admin:back")
    b.adjust(1)
    return b.as_markup()


def admin_roles_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✏️ Назначить роль", callback_data="admin:set_role")
    b.button(text="⬅️ Назад", callback_data="admin:back")
    b.adjust(1)
    return b.as_markup()


def admin_photos_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🎭 Приветствие", callback_data="admin:photo:welcome")
    b.button(text="💳 Реквизиты", callback_data="admin:photo:requisites")
    b.button(text="⏳ Ожидание", callback_data="admin:photo:waiting")
    b.button(text="✅ Успех", callback_data="admin:photo:success")
    b.button(text="⬅️ Назад", callback_data="admin:back")
    b.adjust(2, 2, 1)
    return b.as_markup()


def admin_bank_item_kb(bank_id: int, is_active: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if is_active:
        b.button(text="🚫 Деактивировать", callback_data=f"admin:bank_deact:{bank_id}")
    else:
        b.button(text="✅ Активировать", callback_data=f"admin:bank_act:{bank_id}")
    b.adjust(1)
    return b.as_markup()


def admin_country_item_kb(country_id: int, is_active: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if is_active:
        b.button(text="🚫 Деактивировать", callback_data=f"admin:country_deact:{country_id}")
    else:
        b.button(text="✅ Активировать", callback_data=f"admin:country_act:{country_id}")
    b.adjust(1)
    return b.as_markup()


def admin_choose_role_kb(tg_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for role in ["USER", "MERCHANT", "ADMIN"]:
        b.button(text=role, callback_data=f"admin:role:{tg_id}:{role}")
    b.adjust(3)
    return b.as_markup()


def admin_settings_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📢 Канал (URL)", callback_data="admin:setting:channel_url")
    b.button(text="👨‍💻 Команда (URL)", callback_data="admin:setting:team_url")
    b.button(text="📜 Правила (URL)", callback_data="admin:setting:rules_url")
    b.button(text="🌐 WebApp URL", callback_data="admin:setting:webapp_url")
    b.button(text="📱 ID Канала", callback_data="admin:setting:channel_id")
    b.button(text="💬 Чат мерчантов", callback_data="admin:setting:merchant_chat_id")
    b.button(text="⬅️ Назад", callback_data="admin:back")
    b.adjust(2, 2, 2, 1)
    return b.as_markup()


def confirm_broadcast_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Подтвердить рассылку", callback_data="admin:broadcast_confirm")
    b.button(text="❌ Отменить", callback_data="admin:back")
    b.adjust(1)
    return b.as_markup()


def chat_kb(app_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✉️ Написать", callback_data=f"chat:{app_id}")
    return b.as_markup()


def subscribe_kb(channel_url: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📢 Подписаться", url=channel_url)
    b.button(text="✅ Проверить подписку", callback_data="check_sub")
    b.adjust(1)
    return b.as_markup()


def merchant_taken_kb(app_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="↩️ Вернуть в очередь", callback_data=f"release:{app_id}")
    return b.as_markup()