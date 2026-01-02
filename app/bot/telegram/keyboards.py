"""
Клавиатуры для Telegram бота (inline и reply).
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton


def get_main_keyboard() -> InlineKeyboardMarkup:
    """Возвращает основную inline клавиатуру."""
    keyboard = [
        [
            InlineKeyboardButton("💰 Зарплата", callback_data="salary"),
            InlineKeyboardButton("🌤️ Погода", callback_data="weather"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_reply_keyboard() -> ReplyKeyboardMarkup:
    """Возвращает reply клавиатуру (опционально)."""
    keyboard = [
        [KeyboardButton("💰 Зарплата"), KeyboardButton("🌤️ Погода")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("⚙️ Настройки")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

