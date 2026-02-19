"""
Утилиты для бота
"""
from __future__ import annotations
import random
import string

def gen_payment_code(length: int = 6) -> str:
    """Генерирует случайный код платежа"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def format_amount(amount: float) -> str:
    """Форматирует сумму"""
    return f"{amount:,.2f}".replace(",", " ")

def escape_html(text: str) -> str:
    """Экранирует HTML-символы"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
