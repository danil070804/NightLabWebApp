"""
Модуль push-уведомлений для Telegram бота
"""
from __future__ import annotations
import asyncio
from typing import Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

class NotificationManager:
    """Менеджер уведомлений для пользователей"""
    
    def __init__(self, bot: Bot, db):
        self.bot = bot
        self.db = db
    
    async def send_notification(self, user_tg_id: int, title: str, message: str, 
                                 reply_markup: Optional[InlineKeyboardMarkup] = None,
                                 notification_type: str = "general") -> bool:
        """Отправить уведомление пользователю"""
        try:
            # Сохраняем в БД
            await self.db.create_notification(
                user_tg_id=user_tg_id,
                type=notification_type,
                title=title,
                message=message
            )
            
            # Отправляем в Telegram
            await self.bot.send_message(
                chat_id=user_tg_id,
                text=f"🔔 <b>{title}</b>\n\n{message}",
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            return True
        except Exception as e:
            print(f"Failed to send notification to {user_tg_id}: {e}")
            return False
    
    async def notify_requisites_sent(self, app_id: int, user_tg_id: int, 
                                      bank_name: str, amount: float, 
                                      requisites: str, expires_at: str) -> bool:
        """Уведомление о выдаче реквизитов"""
        from bot.keyboards import i_paid_kb
        
        title = "Реквизиты получены"
        message = (
            f"✅ <b>Заявка #{app_id}</b>\n\n"
            f"🏦 Банк: {bank_name}\n"
            f"💰 Сумма: {amount:.2f} грн\n\n"
            f"<b>Реквизиты:</b>\n"
            f"<code>{requisites}</code>\n\n"
            f"⏳ Оплатите до: {expires_at[:16].replace('T', ' ')}"
        )
        
        return await self.send_notification(
            user_tg_id=user_tg_id,
            title=title,
            message=message,
            reply_markup=i_paid_kb(app_id),
            notification_type="requisites"
        )
    
    async def notify_payment_confirmed(self, app_id: int, user_tg_id: int,
                                        bank_name: str, amount: float) -> bool:
        """Уведомление о подтверждении платежа"""
        title = "Платеж подтвержден"
        message = (
            f"✅ <b>Заявка #{app_id} подтверждена!</b>\n\n"
            f"🏦 Банк: {bank_name}\n"
            f"💰 Сумма: {amount:.2f} грн\n\n"
            f"Спасибо за использование NightLab!"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📄 Мои заявки", callback_data=f"my_apps")]
        ])
        
        return await self.send_notification(
            user_tg_id=user_tg_id,
            title=title,
            message=message,
            reply_markup=keyboard,
            notification_type="confirmed"
        )
    
    async def notify_payment_rejected(self, app_id: int, user_tg_id: int,
                                       bank_name: str, amount: float,
                                       reason: str = "") -> bool:
        """Уведомление об отклонении платежа"""
        title = "Платеж отклонен"
        message = (
            f"❌ <b>Заявка #{app_id} отклонена</b>\n\n"
            f"🏦 Банк: {bank_name}\n"
            f"💰 Сумма: {amount:.2f} грн\n"
        )
        if reason:
            message += f"\nПричина: {reason}"
        
        message += "\n\nОбратитесь в поддержку для уточнения."
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🆘 Поддержка", callback_data=f"support")]
        ])
        
        return await self.send_notification(
            user_tg_id=user_tg_id,
            title=title,
            message=message,
            reply_markup=keyboard,
            notification_type="rejected"
        )
    
    async def notify_app_expired(self, app_id: int, user_tg_id: int) -> bool:
        """Уведомление об истечении времени заявки"""
        title = "Время заявки истекло"
        message = (
            f"⏰ <b>Заявка #{app_id}</b>\n\n"
            f"Время на оплату истекло.\n"
            f"Заявка автоматически закрыта.\n\n"
            f"Создайте новую заявку, если нужно."
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Новая заявка", callback_data=f"new_app")]
        ])
        
        return await self.send_notification(
            user_tg_id=user_tg_id,
            title=title,
            message=message,
            reply_markup=keyboard,
            notification_type="expired"
        )
    
    async def notify_merchant_assigned(self, app_id: int, merchant_tg_id: int,
                                        bank_name: str, amount: float,
                                        user_username: str) -> bool:
        """Уведомление мерчанту о назначении заявки"""
        try:
            message = (
                f"🆕 <b>Новая заявка #{app_id}</b>\n\n"
                f"🏦 Банк: {bank_name}\n"
                f"💰 Сумма: {amount:.2f} грн\n"
                f"👤 Пользователь: @{user_username}\n\n"
                f"Выдайте реквизиты как можно скорее!"
            )
            
            from bot.keyboards import merchant_send_mode_kb
            
            await self.bot.send_message(
                chat_id=merchant_tg_id,
                text=message,
                parse_mode="HTML",
                reply_markup=merchant_send_mode_kb(app_id)
            )
            return True
        except Exception as e:
            print(f"Failed to notify merchant {merchant_tg_id}: {e}")
            return False
    
    async def notify_receipt_received(self, app_id: int, admin_chat_id: int,
                                       user_username: str, amount: float) -> bool:
        """Уведомление админу о получении чека"""
        try:
            message = (
                f"📎 <b>Новый чек к заявке #{app_id}</b>\n\n"
                f"👤 Пользователь: @{user_username}\n"
                f"💰 Сумма: {amount:.2f} грн\n\n"
                f"Проверьте чек и подтвердите платеж!"
            )
            
            from bot.keyboards import check_kb
            
            await self.bot.send_message(
                chat_id=admin_chat_id,
                text=message,
                parse_mode="HTML",
                reply_markup=check_kb(app_id)
            )
            return True
        except Exception as e:
            print(f"Failed to notify admin about receipt: {e}")
            return False
    
    async def notify_new_referral(self, referrer_tg_id: int, 
                                   referred_username: str,
                                   bonus_uah: float = 0) -> bool:
        """Уведомление о новом реферале"""
        title = "Новый реферал"
        message = (
            f"🎉 <b>Поздравляем!</b>\n\n"
            f"@{referred_username} присоединился по вашей ссылке!"
        )
        if bonus_uah > 0:
            message += f"\n💰 Вы получили бонус: {bonus_uah:.2f} грн"
        
        return await self.send_notification(
            user_tg_id=referrer_tg_id,
            title=title,
            message=message,
            notification_type="referral"
        )
    
    async def broadcast_message(self, user_ids: list[int], message: str,
                                 parse_mode: str = "HTML") -> dict:
        """Массовая рассылка сообщений"""
        results = {"sent": 0, "failed": 0}
        
        for user_id in user_ids:
            try:
                await self.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode=parse_mode
                )
                results["sent"] += 1
                await asyncio.sleep(0.05)  # Rate limiting
            except Exception as e:
                print(f"Failed to broadcast to {user_id}: {e}")
                results["failed"] += 1
        
        return results
