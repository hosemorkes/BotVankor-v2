"""
Обработчики команд и сообщений для Telegram бота.
"""

import logging
from telegram import Update
from telegram.error import TimedOut, NetworkError, TelegramError
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
from app.services.weather_service import get_weather, format_weather_report

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
/weather - Получить погоду Ванкорского месторождения
    """
    await update.message.reply_text(help_text)


async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /weather."""
    user = update.effective_user
    loading_msg = None
    
    try:
        # Пытаемся отправить сообщение о загрузке
        try:
            loading_msg = await update.message.reply_text("🌤️ Загружаю данные о погоде...")
        except (TimedOut, NetworkError) as e:
            logger.warning(f"Таймаут при отправке сообщения о загрузке: {e}")
            # Продолжаем без сообщения о загрузке
        
        # Получаем данные о погоде
        weather_data = await get_weather()
        
        if weather_data:
            # Форматируем и отправляем отчёт
            report = format_weather_report(weather_data)
            
            if loading_msg:
                try:
                    await loading_msg.edit_text(report)
                except (TimedOut, NetworkError):
                    # Если не удалось отредактировать, отправляем новое сообщение
                    try:
                        await update.message.reply_text(report)
                    except Exception:
                        logger.error(f"Не удалось отправить погоду пользователю {user.id}")
            else:
                try:
                    await update.message.reply_text(report)
                except Exception:
                    logger.error(f"Не удалось отправить погоду пользователю {user.id}")
            
            # Логируем запрос
            logger.info(f"Пользователь {user.id} запросил погоду")
        else:
            error_msg = (
                "❌ Не удалось получить данные о погоде.\n\n"
                "Возможные причины:\n"
                "• Проблемы с подключением к интернету\n"
                "• Сервис погоды временно недоступен\n"
                "• Не настроен API ключ погоды\n\n"
                "Попробуйте позже или обратитесь к администратору."
            )
            
            if loading_msg:
                try:
                    await loading_msg.edit_text(error_msg)
                except (TimedOut, NetworkError):
                    try:
                        await update.message.reply_text(error_msg)
                    except Exception:
                        pass
            else:
                try:
                    await update.message.reply_text(error_msg)
                except Exception:
                    pass
            
            logger.warning(f"Не удалось получить погоду для пользователя {user.id}")
            
    except (TimedOut, NetworkError) as e:
        error_msg = (
            "❌ Произошла ошибка сети при получении погоды.\n"
            "Проверьте подключение к интернету и попробуйте позже."
        )
        if loading_msg:
            try:
                await loading_msg.edit_text(error_msg)
            except Exception:
                try:
                    await update.message.reply_text(error_msg)
                except Exception:
                    pass
        else:
            try:
                await update.message.reply_text(error_msg)
            except Exception:
                pass
        logger.error(f"Сетевая ошибка при получении погоды для пользователя {user.id}: {e}")
    except Exception as e:
        error_msg = "❌ Произошла ошибка при получении погоды.\nПопробуйте позже."
        if loading_msg:
            try:
                await loading_msg.edit_text(error_msg)
            except Exception:
                try:
                    await update.message.reply_text(error_msg)
                except Exception:
                    pass
        else:
            try:
                await update.message.reply_text(error_msg)
            except Exception:
                pass
        logger.error(f"Ошибка при получении погоды для пользователя {user.id}: {e}")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на inline кнопки."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "salary":
        # TODO: реализовать расчёт зарплаты
        await query.edit_message_text("Функция расчёта зарплаты в разработке")
    elif data == "weather":
        # Получаем погоду
        try:
            await query.answer("Загружаю погоду...")
            weather_data = await get_weather()
            
            if weather_data:
                report = format_weather_report(weather_data)
                await query.edit_message_text(report)
                logger.info(f"Пользователь {query.from_user.id} запросил погоду через кнопку")
            else:
                await query.edit_message_text(
                    "❌ Не удалось получить данные о погоде.\n"
                    "Попробуйте позже."
                )
        except Exception as e:
            await query.edit_message_text(
                "❌ Произошла ошибка при получении погоды."
            )
            logger.error(f"Ошибка при получении погоды через кнопку: {e}")
    else:
        await query.edit_message_text("Неизвестная команда")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений."""
    text = update.message.text
    await update.message.reply_text(
        f"Вы написали: {text}\n\n"
        "Используйте команды или кнопки для взаимодействия."
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик глобальных ошибок."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    # Пытаемся отправить сообщение пользователю об ошибке
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Произошла ошибка при обработке запроса.\n"
                "Попробуйте позже или обратитесь к администратору."
            )
        except Exception:
            # Если не удалось отправить сообщение, просто логируем
            pass


def setup_handlers(application: Application) -> None:
    """Настройка всех обработчиков для приложения."""
    # Команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("weather", weather_command))
    
    # Callback кнопки
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Текстовые сообщения
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    
    # Глобальный обработчик ошибок (должен быть последним)
    application.add_error_handler(error_handler)
    
    logger.info("Обработчики Telegram настроены")

