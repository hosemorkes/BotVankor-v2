"""
Клавиатуры для Telegram бота (inline и reply).
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton


def get_main_keyboard() -> InlineKeyboardMarkup:
    """Возвращает основную inline клавиатуру."""
    keyboard = [
        [
            InlineKeyboardButton("💰 Деньги", callback_data="money_calc"),
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


def get_salary_skip_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру с кнопкой 'Пропустить' для диалога зарплаты."""
    keyboard = [
        [InlineKeyboardButton("⏭️ Пропустить", callback_data="skip")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_salary_confirm_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру подтверждения для диалога зарплаты."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Рассчитать", callback_data="confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_money_calc_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру подменю расчета денег."""
    keyboard = [
        [
            InlineKeyboardButton("💰 Зарплата", callback_data="salary"),
            InlineKeyboardButton("🎁 13-я", callback_data="annual_bonus"),
        ],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="back_to_main"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_back_to_main_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру с кнопкой возврата в главное меню."""
    keyboard = [
        [
            InlineKeyboardButton("◀️ Главное меню", callback_data="back_to_main"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_weather_menu_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру подменю погоды."""
    keyboard = [
        [
            InlineKeyboardButton("🌤️ Погода сегодня", callback_data="weather_today"),
        ],
        [
            InlineKeyboardButton("📅 Погода на 7 дней", callback_data="weather_7days"),
        ],
        [
            InlineKeyboardButton("🚁 Вероятность вылета", callback_data="flight_probability"),
        ],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="back_to_main"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)