"""
Обработчики команд и сообщений для Telegram бота.
"""

import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from app.bot.telegram.keyboards import get_main_keyboard
from app.database.db import get_session, UserCRUD

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start."""
    user = update.effective_user
    
    # Получаем сессию БД
    session = get_session()
    try:
        # Проверяем, существует ли пользователь
        existing_user = UserCRUD.get_by_telegram_id(session, user.id)
        is_new_user = existing_user is None
        
        # Создаём или получаем пользователя
        db_user = UserCRUD.get_or_create(
            session=session,
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        # Логируем вход пользователя
        if is_new_user:
            logger.info(
                f"Новый пользователь зарегистрирован: "
                f"telegram_id={user.id}, username={user.username}, "
                f"first_name={user.first_name}"
            )
        else:
            logger.info(
                f"Пользователь вернулся: "
                f"telegram_id={user.id}, username={user.username}, "
                f"first_name={user.first_name}"
            )
        
        # Формируем приветственное сообщение
        greeting = f"Привет, {user.first_name or 'друг'}! 👋\n\n"
        if is_new_user:
            greeting += "Добро пожаловать! Я бот для работы с зарплатой и погодой."
        else:
            greeting += "С возвращением! Я бот для работы с зарплатой и погодой."
        
        await update.message.reply_text(
            greeting,
            reply_markup=get_main_keyboard()
        )
    finally:
        session.close()


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help."""
    help_text = """
📋 Доступные команды:
/start - Начать работу с ботом
/help - Показать эту справку
/salary - Рассчитать зарплату
/weather - Получить погоду
    """
    await update.message.reply_text(help_text)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на inline кнопки."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "salary":
        # TODO: реализовать расчёт зарплаты
        await query.edit_message_text("Функция расчёта зарплаты в разработке")
    elif data == "weather":
        # TODO: реализовать получение погоды
        await query.edit_message_text("Функция получения погоды в разработке")
    else:
        await query.edit_message_text("Неизвестная команда")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений."""
    text = update.message.text
    await update.message.reply_text(
        f"Вы написали: {text}\n\n"
        "Используйте команды или кнопки для взаимодействия."
    )


def setup_handlers(application: Application) -> None:
    """Настройка всех обработчиков для приложения."""
    # Команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Callback кнопки
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Текстовые сообщения
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    
    logger.info("Обработчики Telegram настроены")

