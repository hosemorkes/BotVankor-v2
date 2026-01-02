"""
Обработчики команд и сообщений для Telegram бота.
"""

import logging
import warnings
from decimal import Decimal, InvalidOperation
from telegram import Update
from telegram.error import TimedOut, NetworkError, TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

from app.bot.telegram.keyboards import get_main_keyboard, get_salary_skip_keyboard, get_salary_confirm_keyboard
from app.database.db import get_session, UserCRUD, SalaryCRUD
from app.services.weather_service import get_weather, format_weather_report
from app.services.salary_service import (
    calculate_salary,
    format_salary_report,
    SalaryCalculationError
)

# Подавляем предупреждение о настройках ConversationHandler
# Текущие настройки корректны для нашего случая использования
warnings.filterwarnings(
    "ignore",
    message=".*per_message=False.*CallbackQueryHandler.*",
    category=UserWarning,
    module="telegram.ext"
)

logger = logging.getLogger(__name__)

# Подавляем предупреждение о настройках ConversationHandler
# Текущие настройки корректны для нашего случая использования
# (per_message=False по умолчанию работает правильно с MessageHandler и CallbackQueryHandler)
try:
    from telegram.warnings import PTBUserWarning
    warnings.filterwarnings("ignore", category=PTBUserWarning)
except ImportError:
    # Если PTBUserWarning недоступен, используем общий фильтр
    warnings.filterwarnings(
        "ignore",
        message=".*per_message=False.*CallbackQueryHandler.*",
        category=UserWarning
    )

# Состояния для диалога расчёта зарплаты
BASE_SALARY, HOURS_WORKED, DISTRICT_COEFFICIENT, NORTHERN_ALLOWANCE, OVERTIME_HOURS, BONUS, CONFIRM = range(7)


async def safe_reply_text(message, text: str, reply_markup=None) -> bool:
    """
    Безопасная отправка текстового сообщения с обработкой сетевых ошибок.
    
    Args:
        message: Объект сообщения (update.message или query.message)
        text: Текст сообщения
        reply_markup: Клавиатура (опционально)
    
    Returns:
        True если сообщение отправлено успешно, False в случае ошибки
    """
    try:
        await message.reply_text(text, reply_markup=reply_markup)
        return True
    except (TimedOut, NetworkError) as e:
        logger.warning(f"Сетевая ошибка при отправке сообщения: {e}")
        return False
    except Exception as e:
        logger.error(f"Неожиданная ошибка при отправке сообщения: {e}")
        return False


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


# Обработчики для диалога расчёта зарплаты
async def salary_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало диалога расчёта зарплаты."""
    await update.message.reply_text(
        "💰 Расчёт зарплаты\n\n"
        "Введите базовую ставку за час (в рублях):\n"
        "Например: 1000"
    )
    return BASE_SALARY


async def salary_start_from_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало диалога расчёта зарплаты из кнопки."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "💰 Расчёт зарплаты\n\n"
        "Введите базовую ставку за час (в рублях):\n"
        "Например: 1000"
    )
    return BASE_SALARY


async def get_base_salary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение базовой ставки."""
    try:
        value = Decimal(update.message.text.replace(",", "."))
        if value <= 0:
            try:
                await update.message.reply_text(
                    "❌ Ставка должна быть больше нуля. Попробуйте ещё раз:"
                )
            except (TimedOut, NetworkError):
                logger.warning(f"Не удалось отправить сообщение пользователю {update.effective_user.id}")
            return BASE_SALARY
        
        context.user_data["base_salary"] = value
        try:
            await update.message.reply_text(
                f"✅ Базовая ставка: {value:.2f} ₽/час\n\n"
                "Введите количество отработанных часов:\n"
                "Например: 160"
            )
        except (TimedOut, NetworkError) as e:
            logger.warning(f"Сетевая ошибка при отправке сообщения пользователю {update.effective_user.id}: {e}")
            # Сохраняем состояние, пользователь может продолжить
        return HOURS_WORKED
    except (ValueError, InvalidOperation):
        try:
            await update.message.reply_text(
                "❌ Неверный формат. Введите число (например: 1000):"
            )
        except (TimedOut, NetworkError):
            logger.warning(f"Не удалось отправить сообщение пользователю {update.effective_user.id}")
        return BASE_SALARY


async def get_hours_worked(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение отработанных часов."""
    try:
        value = Decimal(update.message.text.replace(",", "."))
        if value < 0 or value > 744:
            try:
                await update.message.reply_text(
                    "❌ Количество часов должно быть от 0 до 744. Попробуйте ещё раз:"
                )
            except (TimedOut, NetworkError):
                logger.warning(f"Не удалось отправить сообщение пользователю {update.effective_user.id}")
            return HOURS_WORKED
        
        context.user_data["hours_worked"] = value
        try:
            await update.message.reply_text(
                f"✅ Отработано часов: {value:.0f}\n\n"
                "Введите районный коэффициент (например: 1.5)\n"
                "Или нажмите 'Пропустить' для значения по умолчанию (1.0):",
                reply_markup=get_salary_skip_keyboard()
            )
        except (TimedOut, NetworkError) as e:
            logger.warning(f"Сетевая ошибка при отправке сообщения пользователю {update.effective_user.id}: {e}")
        return DISTRICT_COEFFICIENT
    except (ValueError, InvalidOperation):
        try:
            await update.message.reply_text(
                "❌ Неверный формат. Введите число (например: 160):"
            )
        except (TimedOut, NetworkError):
            logger.warning(f"Не удалось отправить сообщение пользователю {update.effective_user.id}")
        return HOURS_WORKED


async def get_district_coefficient(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение районного коэффициента."""
    if update.callback_query:
        # Обработка кнопки "Пропустить"
        await update.callback_query.answer()
        context.user_data["district_coefficient"] = None
        coeff_text = "1.0 (по умолчанию)"
        message = update.callback_query.message
    else:
        # Обработка текстового ввода
        text = update.message.text.strip()
        if text.lower() in ["пропустить", "skip", "далее"]:
            context.user_data["district_coefficient"] = None
            coeff_text = "1.0 (по умолчанию)"
        else:
            try:
                value = Decimal(text.replace(",", "."))
                if value < 1.0 or value > 3.0:
                    await update.message.reply_text(
                        "❌ Коэффициент должен быть от 1.0 до 3.0. Попробуйте ещё раз:",
                        reply_markup=get_salary_skip_keyboard()
                    )
                    return DISTRICT_COEFFICIENT
                context.user_data["district_coefficient"] = value
                coeff_text = f"{value:.2f}"
            except (ValueError, InvalidOperation):
                await update.message.reply_text(
                    "❌ Неверный формат. Введите число (например: 1.5) или 'Пропустить':",
                    reply_markup=get_salary_skip_keyboard()
                )
                return DISTRICT_COEFFICIENT
        message = update.message
    
    await message.reply_text(
        f"✅ Районный коэффициент: {coeff_text}\n\n"
        "Введите процент северной надбавки (0-100):\n"
        "Или нажмите 'Пропустить':",
        reply_markup=get_salary_skip_keyboard()
    )
    return NORTHERN_ALLOWANCE


async def get_northern_allowance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение северной надбавки."""
    if update.callback_query:
        # Обработка кнопки "Пропустить"
        await update.callback_query.answer()
        context.user_data["northern_allowance_rate"] = None
        allowance_text = "0% (по умолчанию)"
    else:
        # Обработка текстового ввода
        text = update.message.text.strip()
        if text.lower() in ["пропустить", "skip", "далее"]:
            context.user_data["northern_allowance_rate"] = None
            allowance_text = "0% (по умолчанию)"
        else:
            try:
                value = Decimal(text.replace(",", "."))
                if value < 0 or value > 100:
                    await update.message.reply_text(
                        "❌ Процент должен быть от 0 до 100. Попробуйте ещё раз:",
                        reply_markup=get_salary_skip_keyboard()
                    )
                    return NORTHERN_ALLOWANCE
                context.user_data["northern_allowance_rate"] = value
                allowance_text = f"{value:.1f}%"
            except (ValueError, InvalidOperation):
                await update.message.reply_text(
                    "❌ Неверный формат. Введите число (например: 50) или 'Пропустить':",
                    reply_markup=get_salary_skip_keyboard()
                )
                return NORTHERN_ALLOWANCE
    
    message = update.callback_query.message if update.callback_query else update.message
    await message.reply_text(
        f"✅ Северная надбавка: {allowance_text}\n\n"
        "Введите количество переработанных часов:\n"
        "Или нажмите 'Пропустить':",
        reply_markup=get_salary_skip_keyboard()
    )
    return OVERTIME_HOURS


async def get_overtime_hours(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение переработанных часов."""
    if update.callback_query:
        # Обработка кнопки "Пропустить"
        await update.callback_query.answer()
        context.user_data["overtime_hours"] = None
        overtime_text = "0 ч (по умолчанию)"
    else:
        # Обработка текстового ввода
        text = update.message.text.strip()
        if text.lower() in ["пропустить", "skip", "далее"]:
            context.user_data["overtime_hours"] = None
            overtime_text = "0 ч (по умолчанию)"
        else:
            try:
                value = Decimal(text.replace(",", "."))
                if value < 0:
                    await update.message.reply_text(
                        "❌ Количество часов не может быть отрицательным. Попробуйте ещё раз:",
                        reply_markup=get_salary_skip_keyboard()
                    )
                    return OVERTIME_HOURS
                if value > context.user_data.get("hours_worked", Decimal("0")):
                    await update.message.reply_text(
                        "❌ Переработанные часы не могут превышать отработанные. Попробуйте ещё раз:",
                        reply_markup=get_salary_skip_keyboard()
                    )
                    return OVERTIME_HOURS
                context.user_data["overtime_hours"] = value
                overtime_text = f"{value:.0f} ч"
            except (ValueError, InvalidOperation):
                await update.message.reply_text(
                    "❌ Неверный формат. Введите число (например: 20) или 'Пропустить':",
                    reply_markup=get_salary_skip_keyboard()
                )
                return OVERTIME_HOURS
    
    message = update.callback_query.message if update.callback_query else update.message
    await message.reply_text(
        f"✅ Переработки: {overtime_text}\n\n"
        "Введите размер бонуса (в рублях):\n"
        "Или нажмите 'Пропустить':",
        reply_markup=get_salary_skip_keyboard()
    )
    return BONUS


async def get_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение бонуса."""
    if update.callback_query:
        # Обработка кнопки "Пропустить"
        await update.callback_query.answer()
        context.user_data["bonus"] = None
        bonus_text = "0 ₽ (по умолчанию)"
    else:
        # Обработка текстового ввода
        text = update.message.text.strip()
        if text.lower() in ["пропустить", "skip", "далее"]:
            context.user_data["bonus"] = None
            bonus_text = "0 ₽ (по умолчанию)"
        else:
            try:
                value = Decimal(text.replace(",", "."))
                if value < 0:
                    await update.message.reply_text(
                        "❌ Бонус не может быть отрицательным. Попробуйте ещё раз:",
                        reply_markup=get_salary_skip_keyboard()
                    )
                    return BONUS
                context.user_data["bonus"] = value
                bonus_text = f"{value:.2f} ₽"
            except (ValueError, InvalidOperation):
                await update.message.reply_text(
                    "❌ Неверный формат. Введите число (например: 20000) или 'Пропустить':",
                    reply_markup=get_salary_skip_keyboard()
                )
                return BONUS
    
    # Формируем сводку для подтверждения
    summary = "📋 Проверьте введённые данные:\n\n"
    summary += f"💰 Базовая ставка: {context.user_data['base_salary']:.2f} ₽/час\n"
    summary += f"⏰ Отработано часов: {context.user_data['hours_worked']:.0f}\n"
    
    coeff = context.user_data.get("district_coefficient")
    coeff_text = f"{coeff:.2f}" if coeff else "1.0 (по умолчанию)"
    summary += f"📍 Районный коэффициент: {coeff_text}\n"
    
    allowance = context.user_data.get("northern_allowance_rate")
    allowance_text = f"{allowance:.1f}%" if allowance else "0% (по умолчанию)"
    summary += f"❄️ Северная надбавка: {allowance_text}\n"
    
    overtime = context.user_data.get("overtime_hours")
    overtime_text = f"{overtime:.0f} ч" if overtime else "0 ч (по умолчанию)"
    summary += f"⏱️ Переработки: {overtime_text}\n"
    
    bonus = context.user_data.get("bonus")
    bonus_text = f"{bonus:.2f} ₽" if bonus else "0 ₽ (по умолчанию)"
    summary += f"🎁 Бонус: {bonus_text}\n\n"
    summary += "Нажмите 'Рассчитать' для выполнения расчёта или 'Отмена' для выхода:"
    
    message = update.callback_query.message if update.callback_query else update.message
    await message.reply_text(
        summary,
        reply_markup=get_salary_confirm_keyboard()
    )
    return CONFIRM


async def confirm_salary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждение и расчёт зарплаты."""
    user = update.effective_user
    query = update.callback_query
    
    if query:
        await query.answer()
    
    try:
        # Выполняем расчёт
        calculation = calculate_salary(
            base_salary=context.user_data["base_salary"],
            hours_worked=context.user_data["hours_worked"],
            bonus=context.user_data.get("bonus"),
            northern_allowance_rate=context.user_data.get("northern_allowance_rate"),
            district_coefficient=context.user_data.get("district_coefficient"),
            overtime_hours=context.user_data.get("overtime_hours")
        )
        
        # Форматируем отчёт
        report = format_salary_report(calculation)
        
        # Сохраняем в БД
        session = get_session()
        try:
            db_user = UserCRUD.get_by_telegram_id(session, user.id)
            if db_user:
                SalaryCRUD.create(
                    session=session,
                    user_id=db_user.id,
                    base_salary=float(calculation["base_salary"]),
                    hours_worked=float(calculation["hours_worked"]),
                    gross=float(calculation["gross"]),
                    gross_with_coefficient=float(calculation["gross_with_coefficient"]),
                    total=float(calculation["total"]),
                    tax=float(calculation["tax"]),
                    net=float(calculation["net"]),
                    district_coefficient=float(calculation["district_coefficient"]),
                    northern_allowance_rate=float(context.user_data.get("northern_allowance_rate") or 0),
                    northern_allowance=float(calculation["northern_allowance"]),
                    overtime_hours=float(calculation["overtime_hours"]),
                    overtime_pay=float(calculation["overtime_pay"]),
                    bonus=float(calculation["bonus"])
                )
                logger.info(f"Сохранён расчёт зарплаты для user_id={user.id}")
        finally:
            session.close()
        
        message = query.message if query else update.message
        await message.reply_text(
            report + "\n\n✅ Расчёт сохранён в базе данных.",
            reply_markup=get_main_keyboard()
        )
        
        # Очищаем данные диалога
        context.user_data.clear()
        return ConversationHandler.END
        
    except SalaryCalculationError as e:
        message = query.message if query else update.message
        await message.reply_text(
            f"❌ Ошибка расчёта: {e}\n\n"
            "Попробуйте начать заново командой /salary",
            reply_markup=get_main_keyboard()
        )
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка при расчёте зарплаты для user_id={user.id}: {e}", exc_info=True)
        message = query.message if query else update.message
        await message.reply_text(
            "❌ Произошла ошибка при расчёте зарплаты.\n"
            "Попробуйте позже или обратитесь к администратору.",
            reply_markup=get_main_keyboard()
        )
        context.user_data.clear()
        return ConversationHandler.END


async def cancel_salary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена расчёта зарплаты."""
    query = update.callback_query
    if query:
        await query.answer()
    
    context.user_data.clear()
    message = query.message if query else update.message
    await message.reply_text(
        "❌ Расчёт зарплаты отменён.",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на inline кнопки."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    # Игнорируем кнопки, которые обрабатываются ConversationHandler
    if data in ["salary", "skip", "confirm", "cancel"]:
        return
    
    if data == "weather":
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
    error = context.error
    
    # Обработка сетевых ошибок (временные проблемы с подключением)
    if isinstance(error, (NetworkError, TimedOut)):
        logger.warning(f"Сетевая ошибка при обработке обновления: {error}")
        # Не отправляем сообщение пользователю при сетевых ошибках - это временная проблема
        # Пользователь может повторить запрос позже
        return
    
    # Логируем другие ошибки
    logger.error(f"Exception while handling an update: {error}", exc_info=error)
    
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
    # Диалог расчёта зарплаты (должен быть перед другими обработчиками)
    salary_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("salary", salary_start),
            CallbackQueryHandler(salary_start_from_button, pattern="^salary$")
        ],
        states={
            BASE_SALARY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_base_salary)],
            HOURS_WORKED: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_hours_worked)],
            DISTRICT_COEFFICIENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_district_coefficient),
                CallbackQueryHandler(get_district_coefficient, pattern="^skip$")
            ],
            NORTHERN_ALLOWANCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_northern_allowance),
                CallbackQueryHandler(get_northern_allowance, pattern="^skip$")
            ],
            OVERTIME_HOURS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_overtime_hours),
                CallbackQueryHandler(get_overtime_hours, pattern="^skip$")
            ],
            BONUS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_bonus),
                CallbackQueryHandler(get_bonus, pattern="^skip$")
            ],
            CONFIRM: [
                CallbackQueryHandler(confirm_salary, pattern="^confirm$"),
                CallbackQueryHandler(cancel_salary, pattern="^cancel$")
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_salary),
            CommandHandler("start", cancel_salary),
        ],
        # per_chat=True по умолчанию - состояние отслеживается отдельно для каждого чата
        # per_message=False по умолчанию - это нормально для нашего случая с MessageHandler и CallbackQueryHandler
    )
    application.add_handler(salary_conv_handler)
    
    # Команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("weather", weather_command))
    
    # Callback кнопки (обрабатывает только не-salary кнопки, так как salary обрабатывается в ConversationHandler)
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Текстовые сообщения
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    
    # Глобальный обработчик ошибок (должен быть последним)
    application.add_error_handler(error_handler)
    
    logger.info("Обработчики Telegram настроены")

