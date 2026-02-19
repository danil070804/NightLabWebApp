from aiogram.fsm.state import State, StatesGroup

class UserFlow(StatesGroup):
    choosing_country = State()
    choosing_bank = State()
    entering_amount = State()

class MerchantFlow(StatesGroup):
    choosing_send_mode = State()
    entering_requisites = State()

class AdminFlow(StatesGroup):
    entering_bank_name = State()
    entering_requisites_text = State()
    entering_country_name = State()
    entering_user_id = State()
    entering_setting_value = State()
    entering_broadcast = State()
    entering_photo = State()
    entering_reject_reason = State()

class ChatFlow(StatesGroup):
    chatting = State()
