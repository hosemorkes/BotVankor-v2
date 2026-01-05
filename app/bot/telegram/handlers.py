"""
Обработчики команд и сообщений для Telegram бота.
"""

import logging
import warnings
import asyncio
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

from app.bot.telegram.keyboards import (
    get_main_keyboard,
    get_salary_confirm_keyboard,
    get_money_calc_keyboard,
    get_back_to_main_keyboard,
    get_weather_menu_keyboard
)
from app.database.db import db_session, UserCRUD, SalaryCRUD
from app.services.weather_service import get_weather, format_weather_report
from app.services.seven_day_weather import get_7_day_forecast, format_7_day_forecast_report
from app.services.flight_forecast_weather import get_flight_forecast, format_flight_forecast_report
from app.services.salary_service import (
    calculate_salary,
    format_salary_report,
    SalaryCalculationError
)
from app.services.annual_bonus_service import (
    calculate_annual_bonus,
    format_annual_bonus_report,
    AnnualBonusCalculationError
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
HOURLY_RATE, DAYS_WORKED, NIGHT_HOURS, IDLE_DAYS, TRAVEL_DAYS, HOLIDAY_DAYS, ADDITIONAL_PAYMENTS, REGIONAL_ALLOWANCE, NORTHERN_ALLOWANCE, CONFIRM = range(10)

# Состояния для диалога расчёта 13-й зарплаты
ANNUAL_HOURLY_RATE, ANNUAL_MONTHS, ANNUAL_BONUS_RATE, ANNUAL_TARGET_BONUS_RATE, ANNUAL_KPI, ANNUAL_CORRECTION_COEFFICIENT = range(10, 16)
# Состояния для ввода дней по месяцам (M1-M12)
ANNUAL_MONTH_1, ANNUAL_MONTH_2, ANNUAL_MONTH_3, ANNUAL_MONTH_4, ANNUAL_MONTH_5, ANNUAL_MONTH_6, \
ANNUAL_MONTH_7, ANNUAL_MONTH_8, ANNUAL_MONTH_9, ANNUAL_MONTH_10, ANNUAL_MONTH_11, ANNUAL_MONTH_12 = range(16, 28)
ANNUAL_REGIONAL, ANNUAL_NORTHERN, ANNUAL_CONFIRM = range(28, 31)


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
    
    # Используем контекстный менеджер для безопасной работы с БД
    with db_session() as session:
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
                    await loading_msg.edit_text(
                        report,
                        reply_markup=get_back_to_main_keyboard()
                    )
                except (TimedOut, NetworkError):
                    # Если не удалось отредактировать, отправляем новое сообщение
                    try:
                        await update.message.reply_text(
                            report,
                            reply_markup=get_back_to_main_keyboard()
                        )
                    except Exception:
                        logger.error(f"Не удалось отправить погоду пользователю {user.id}")
            else:
                try:
                    await update.message.reply_text(
                        report,
                        reply_markup=get_back_to_main_keyboard()
                    )
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
        "💰 Введите часовую ставку (в рублях):\n"
        "Например: 1000"
    )
    return HOURLY_RATE


async def salary_start_from_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало диалога расчёта зарплаты из кнопки."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "💰 Введите часовую ставку (в рублях):\n"
        "Например: 1000"
    )
    return HOURLY_RATE


async def get_hourly_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение часовой ставки."""
    try:
        value = Decimal(update.message.text.replace(",", "."))
        if value <= 0:
            try:
                await update.message.reply_text(
                    "❌ Ставка должна быть больше нуля. Попробуйте ещё раз:"
                )
            except (TimedOut, NetworkError):
                logger.warning(f"Не удалось отправить сообщение пользователю {update.effective_user.id}")
            return HOURLY_RATE
        
        context.user_data["hourly_rate"] = value
        try:
            await update.message.reply_text(
                "📅 Введите количество отработанных дней:\n"
                "Например: 15"
            )
        except (TimedOut, NetworkError) as e:
            logger.warning(f"Сетевая ошибка при отправке сообщения пользователю {update.effective_user.id}: {e}")
        return DAYS_WORKED
    except (ValueError, InvalidOperation):
        try:
            await update.message.reply_text(
                "❌ Неверный формат. Введите число (например: 1000):"
            )
        except (TimedOut, NetworkError):
            logger.warning(f"Не удалось отправить сообщение пользователю {update.effective_user.id}")
        return HOURLY_RATE


async def get_days_worked(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение отработанных дней."""
    try:
        value = Decimal(update.message.text.replace(",", "."))
        if value < 0 or value > 365:
            try:
                await update.message.reply_text(
                    "❌ Количество дней должно быть от 0 до 365. Попробуйте ещё раз:"
                )
            except (TimedOut, NetworkError):
                logger.warning(f"Не удалось отправить сообщение пользователю {update.effective_user.id}")
            return DAYS_WORKED
        
        context.user_data["days_worked"] = value
        try:
            await update.message.reply_text(
                "🌙 Введите количество ночных смен (в часах):"
            )
        except (TimedOut, NetworkError) as e:
            logger.warning(f"Сетевая ошибка при отправке сообщения пользователю {update.effective_user.id}: {e}")
        return NIGHT_HOURS
    except (ValueError, InvalidOperation):
        try:
            await update.message.reply_text(
                "❌ Неверный формат. Введите число (например: 15):"
            )
        except (TimedOut, NetworkError):
            logger.warning(f"Не удалось отправить сообщение пользователю {update.effective_user.id}")
        return DAYS_WORKED


async def get_night_hours(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение ночных часов."""
    try:
        text = update.message.text.strip()
        value = Decimal(text.replace(",", "."))
        if value < 0:
            await update.message.reply_text(
                "❌ Количество часов не может быть отрицательным. Попробуйте ещё раз:"
            )
            return NIGHT_HOURS
        context.user_data["night_hours"] = value
    except (ValueError, InvalidOperation):
        await update.message.reply_text(
            "❌ Неверный формат. Введите число (например: 20 или 0):"
        )
        return NIGHT_HOURS
    
    await update.message.reply_text(
        "⏸️ Введите количество дней простоя:"
    )
    return IDLE_DAYS


async def get_idle_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение дней простоя."""
    try:
        text = update.message.text.strip()
        value = Decimal(text.replace(",", "."))
        if value < 0:
            await update.message.reply_text(
                "❌ Количество дней не может быть отрицательным. Попробуйте ещё раз:"
            )
            return IDLE_DAYS
        context.user_data["idle_days"] = value
    except (ValueError, InvalidOperation):
        await update.message.reply_text(
            "❌ Неверный формат. Введите число (например: 2 или 0):"
        )
        return IDLE_DAYS
    
    await update.message.reply_text(
        "🚗 Введите дни в пути:"
    )
    return TRAVEL_DAYS


async def get_travel_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение дней в пути."""
    try:
        text = update.message.text.strip()
        value = Decimal(text.replace(",", "."))
        if value < 0:
            await update.message.reply_text(
                "❌ Количество дней не может быть отрицательным. Попробуйте ещё раз:"
            )
            return TRAVEL_DAYS
        context.user_data["travel_days"] = value
    except (ValueError, InvalidOperation):
        await update.message.reply_text(
            "❌ Неверный формат. Введите число (например: 2 или 0):"
        )
        return TRAVEL_DAYS
    
    await update.message.reply_text(
        "🎉 Введите количество праздничных дней:"
    )
    return HOLIDAY_DAYS


async def get_holiday_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение праздничных дней."""
    try:
        text = update.message.text.strip()
        value = Decimal(text.replace(",", "."))
        if value < 0:
            await update.message.reply_text(
                "❌ Количество дней не может быть отрицательным. Попробуйте ещё раз:"
            )
            return HOLIDAY_DAYS
        context.user_data["holiday_days"] = value
    except (ValueError, InvalidOperation):
        await update.message.reply_text(
            "❌ Неверный формат. Введите число (например: 1 или 0):"
        )
        return HOLIDAY_DAYS
    
    await update.message.reply_text(
        "➕ Введите премии и прочие доплаты (в рублях):"
    )
    return ADDITIONAL_PAYMENTS


async def get_additional_payments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение прочих доплат."""
    try:
        text = update.message.text.strip()
        value = Decimal(text.replace(",", "."))
        if value < 0:
            await update.message.reply_text(
                "❌ Сумма не может быть отрицательной. Попробуйте ещё раз:"
            )
            return ADDITIONAL_PAYMENTS
        context.user_data["additional_payments"] = value
    except (ValueError, InvalidOperation):
        await update.message.reply_text(
            "❌ Неверный формат. Введите число (например: 5000 или 0):"
        )
        return ADDITIONAL_PAYMENTS
    
    await update.message.reply_text(
        "📍 Введите региональную надбавку в процентах (0-100):\n"
        "На ванкоре в основном 60%"
    )
    return REGIONAL_ALLOWANCE


async def get_regional_allowance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение региональной надбавки."""
    try:
        text = update.message.text.strip()
        value = Decimal(text.replace(",", "."))
        if value < 0 or value > 100:
            await update.message.reply_text(
                "❌ Процент должен быть от 0 до 100. Попробуйте ещё раз:"
            )
            return REGIONAL_ALLOWANCE
        context.user_data["regional_allowance_rate"] = value
    except (ValueError, InvalidOperation):
        await update.message.reply_text(
            "❌ Неверный формат. Введите число (например: 60 или 0):"
        )
        return REGIONAL_ALLOWANCE
    
    await update.message.reply_text(
        "❄️ Введите северную надбавку в процентах (0-100):"
    )
    return NORTHERN_ALLOWANCE


async def get_northern_allowance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение северной надбавки."""
    try:
        text = update.message.text.strip()
        value = Decimal(text.replace(",", "."))
        if value < 0 or value > 100:
            await update.message.reply_text(
                "❌ Процент должен быть от 0 до 100. Попробуйте ещё раз:"
            )
            return NORTHERN_ALLOWANCE
        context.user_data["northern_allowance_rate"] = value
    except (ValueError, InvalidOperation):
        await update.message.reply_text(
            "❌ Неверный формат. Введите число (например: 50 или 0):"
        )
        return NORTHERN_ALLOWANCE
    
    # Формируем сводку для подтверждения
    summary = "📋 Проверьте введённые данные:\n\n"
    summary += f"💰 Часовая ставка: {context.user_data['hourly_rate']:.2f} ₽/час\n"
    summary += f"📅 Отработано дней: {context.user_data['days_worked']:.0f}\n"
    
    night = context.user_data.get("night_hours") or Decimal("0")
    summary += f"🌙 Ночные часы: {night:.1f} ч\n"
    
    idle = context.user_data.get("idle_days") or Decimal("0")
    summary += f"⏸️ Дни простоя: {idle:.0f} дн.\n"
    
    travel = context.user_data.get("travel_days") or Decimal("0")
    summary += f"🚗 Дни в пути: {travel:.0f} дн.\n"
    
    holiday = context.user_data.get("holiday_days") or Decimal("0")
    summary += f"🎉 Праздничные дни: {holiday:.0f} дн.\n"
    
    payments = context.user_data.get("additional_payments") or Decimal("0")
    summary += f"➕ Прочие доплаты: {payments:.2f} ₽\n"
    
    regional = context.user_data.get("regional_allowance_rate") or Decimal("0")
    summary += f"📍 Региональная надбавка: {regional:.1f}%\n"
    
    northern = context.user_data.get("northern_allowance_rate") or Decimal("0")
    summary += f"❄️ Северная надбавка: {northern:.1f}%\n\n"
    summary += "Нажмите 'Рассчитать' для выполнения расчёта или 'Отмена' для выхода:"
    
    await update.message.reply_text(
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
            hourly_rate=context.user_data["hourly_rate"],
            days_worked=context.user_data["days_worked"],
            night_hours=context.user_data.get("night_hours"),
            idle_days=context.user_data.get("idle_days"),
            travel_days=context.user_data.get("travel_days"),
            holiday_days=context.user_data.get("holiday_days"),
            additional_payments=context.user_data.get("additional_payments"),
            regional_allowance_rate=context.user_data.get("regional_allowance_rate"),
            northern_allowance_rate=context.user_data.get("northern_allowance_rate")
        )
        
        # Форматируем отчёт
        report = format_salary_report(calculation)
        
        # Сохраняем в БД используя контекстный менеджер
        with db_session() as session:
            SalaryCRUD.create(
                session=session,
                telegram_id=user.id,
                username=user.username,
                hourly_rate=float(calculation["hourly_rate"]),
                days_worked=float(calculation["days_worked"]),
                night_hours=float(calculation["night_hours"]),
                travel_days=float(calculation["travel_days"]),
                holiday_days=float(calculation["holiday_days"]),
                idle_days=float(calculation["idle_days"]),
                additional_payments=float(calculation["additional_payments"]),
                salary_by_position=float(calculation["salary_by_position"]),
                shift_method_payment=float(calculation["shift_method_payment"]),
                monthly_bonus=float(calculation["monthly_bonus"]),
                regional_allowance=float(calculation["regional_allowance"]),
                northern_allowance=float(calculation["northern_allowance"]),
                net=float(calculation["net"])
            )
            logger.info(f"Сохранён расчёт зарплаты для telegram_id={user.id}")
        
        message = query.message if query else update.message
        await message.reply_text(
            report,
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


# Обработчики для диалога расчёта 13-й зарплаты
async def annual_bonus_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало диалога расчёта 13-й зарплаты."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎁 Введите часовую ставку (в рублях):\n"
        "Например: 1000"
    )
    return ANNUAL_HOURLY_RATE


async def get_annual_hourly_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение часовой ставки для 13-й зарплаты."""
    try:
        value = Decimal(update.message.text.replace(",", "."))
        if value <= 0:
            await update.message.reply_text(
                "❌ Ставка должна быть больше нуля. Попробуйте ещё раз:"
            )
            return ANNUAL_HOURLY_RATE
        
        context.user_data["annual_hourly_rate"] = value
        await update.message.reply_text(
            "📅 Введите количество месяцев в компании за год (1-12):\n"
            "Межвахтовый отдых считается"
        )
        return ANNUAL_MONTHS
    except (ValueError, InvalidOperation):
        await update.message.reply_text(
            "❌ Неверный формат. Введите число (например: 1000):"
        )
        return ANNUAL_HOURLY_RATE


async def get_annual_months(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение количества месяцев в компании."""
    try:
        value = Decimal(update.message.text.replace(",", "."))
        if value < 1 or value > 12:
            await update.message.reply_text(
                "❌ Количество месяцев должно быть от 1 до 12. Попробуйте ещё раз:"
            )
            return ANNUAL_MONTHS
        
        context.user_data["annual_months"] = value
        await update.message.reply_text(
            "📈 Введите средний % ежемесячной премии за год (0-100):\n"
            "По умолчанию: 33\n"
            "Можно ввести число или нажать 'Пропустить' для значения по умолчанию"
        )
        return ANNUAL_BONUS_RATE
    except (ValueError, InvalidOperation):
        await update.message.reply_text(
            "❌ Неверный формат. Введите число от 1 до 12:"
        )
        return ANNUAL_MONTHS


async def get_annual_bonus_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение процента ежемесячной премии."""
    text = update.message.text.strip().lower()
    
    # Проверяем, хочет ли пользователь пропустить (использовать значение по умолчанию)
    if text in ["пропустить", "skip", "по умолчанию", "default", ""]:
        context.user_data["annual_bonus_rate"] = None  # Будет использовано значение по умолчанию
    else:
        try:
            value = Decimal(text.replace(",", "."))
            if value < 0 or value > 100:
                await update.message.reply_text(
                    "❌ Процент должен быть от 0 до 100. Попробуйте ещё раз:"
                )
                return ANNUAL_BONUS_RATE
            context.user_data["annual_bonus_rate"] = value
        except (ValueError, InvalidOperation):
            await update.message.reply_text(
                "❌ Неверный формат. Введите число от 0 до 100 или 'Пропустить':"
            )
            return ANNUAL_BONUS_RATE
    
    await update.message.reply_text(
        "🎯 Введите целевой % годового вознаграждения по должности (0-100):\n"
        "Например:\n"
        "• Руководители: 28.25%\n"
        "• Специалисты, служащие: 19.58%\n"
        "• Рабочие: 12.40%"
    )
    return ANNUAL_TARGET_BONUS_RATE


async def get_annual_target_bonus_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение целевого % годового вознаграждения по должности."""
    try:
        text = update.message.text.strip()
        value = Decimal(text.replace(",", "."))
        if value < 0 or value > 100:
            await update.message.reply_text(
                "❌ Процент должен быть от 0 до 100. Попробуйте ещё раз:"
            )
            return ANNUAL_TARGET_BONUS_RATE
        context.user_data["annual_target_bonus_rate"] = value
    except (ValueError, InvalidOperation):
        await update.message.reply_text(
            "❌ Неверный формат. Введите число от 0 до 100 (например: 19.58):"
        )
        return ANNUAL_TARGET_BONUS_RATE
    
    await update.message.reply_text(
        "🎯 Введите коэффициент выполнения (KPI) (например: 1.0):\n"
        "По умолчанию: 1.0\n"
        "Можно ввести число или нажать 'Пропустить' для значения по умолчанию"
    )
    return ANNUAL_KPI


async def get_annual_kpi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение коэффициента выполнения (KPI)."""
    text = update.message.text.strip().lower()
    
    # Проверяем, хочет ли пользователь пропустить (использовать значение по умолчанию)
    if text in ["пропустить", "skip", "по умолчанию", "default", ""]:
        context.user_data["annual_kpi"] = None  # Будет использовано значение по умолчанию
    else:
        try:
            value = Decimal(text.replace(",", "."))
            if value < 0:
                await update.message.reply_text(
                    "❌ Коэффициент не может быть отрицательным. Попробуйте ещё раз:"
                )
                return ANNUAL_KPI
            context.user_data["annual_kpi"] = value
        except (ValueError, InvalidOperation):
            await update.message.reply_text(
                "❌ Неверный формат. Введите число (например: 1.0) или 'Пропустить':"
            )
            return ANNUAL_KPI
    
    await update.message.reply_text(
        "⚖️ Введите корректирующий коэффициент (например: 1.0):\n"
        "По умолчанию: 1.0 (обычно 1.0, если нет взысканий)\n"
        "Можно ввести число или нажать 'Пропустить' для значения по умолчанию"
    )
    return ANNUAL_CORRECTION_COEFFICIENT


async def get_annual_correction_coefficient(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение корректирующего коэффициента."""
    text = update.message.text.strip().lower()
    
    # Проверяем, хочет ли пользователь пропустить (использовать значение по умолчанию)
    if text in ["пропустить", "skip", "по умолчанию", "default", ""]:
        context.user_data["annual_correction_coefficient"] = None  # Будет использовано значение по умолчанию
    else:
        try:
            value = Decimal(text.replace(",", "."))
            if value < 0:
                await update.message.reply_text(
                    "❌ Коэффициент не может быть отрицательным. Попробуйте ещё раз:"
                )
                return ANNUAL_CORRECTION_COEFFICIENT
            context.user_data["annual_correction_coefficient"] = value
        except (ValueError, InvalidOperation):
            await update.message.reply_text(
                "❌ Неверный формат. Введите число (например: 1.0) или 'Пропустить':"
            )
            return ANNUAL_CORRECTION_COEFFICIENT
    
    # Инициализируем словарь для дней по месяцам
    if "annual_monthly_days" not in context.user_data:
        context.user_data["annual_monthly_days"] = {}
    
    await update.message.reply_text(
        "📅 Теперь введите количество дней на вахте по месяцам.\n\n"
        "Январь — дней на вахте:\n"
        "(Если не работали в этом месяце, введите 0)"
    )
    return ANNUAL_MONTH_1


# Обработчики для ввода дней по месяцам
MONTH_NAMES = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
}

MONTH_STATES = {
    1: ANNUAL_MONTH_1, 2: ANNUAL_MONTH_2, 3: ANNUAL_MONTH_3, 4: ANNUAL_MONTH_4,
    5: ANNUAL_MONTH_5, 6: ANNUAL_MONTH_6, 7: ANNUAL_MONTH_7, 8: ANNUAL_MONTH_8,
    9: ANNUAL_MONTH_9, 10: ANNUAL_MONTH_10, 11: ANNUAL_MONTH_11, 12: ANNUAL_MONTH_12
}


async def get_annual_month_days(update: Update, context: ContextTypes.DEFAULT_TYPE, month_num: int) -> int:
    """Получение дней на вахте для указанного месяца."""
    try:
        text = update.message.text.strip()
        value = Decimal(text.replace(",", "."))
        if value < 0:
            await update.message.reply_text(
                f"❌ Количество дней не может быть отрицательным. Попробуйте ещё раз:"
            )
            return MONTH_STATES[month_num]
        if value > 31:
            await update.message.reply_text(
                f"❌ Количество дней не может быть больше 31. Попробуйте ещё раз:"
            )
            return MONTH_STATES[month_num]
        
        context.user_data["annual_monthly_days"][month_num] = value
        
        # Если это не последний месяц, переходим к следующему
        if month_num < 12:
            next_month = month_num + 1
            await update.message.reply_text(
                f"{MONTH_NAMES[next_month]} — дней на вахте:\n"
                "(Если не работали в этом месяце, введите 0)"
            )
            return MONTH_STATES[next_month]
        else:
            # Все месяцы введены, переходим к региональной надбавке
            await update.message.reply_text(
                "📍 Введите региональную надбавку в процентах (0-100):\n"
                "На ванкоре в основном 60%"
            )
            return ANNUAL_REGIONAL
    except (ValueError, InvalidOperation):
        await update.message.reply_text(
            f"❌ Неверный формат. Введите число (например: 15 или 0):"
        )
        return MONTH_STATES[month_num]


async def get_annual_month_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение дней на вахте для января."""
    return await get_annual_month_days(update, context, 1)


async def get_annual_month_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение дней на вахте для февраля."""
    return await get_annual_month_days(update, context, 2)


async def get_annual_month_3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение дней на вахте для марта."""
    return await get_annual_month_days(update, context, 3)


async def get_annual_month_4(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение дней на вахте для апреля."""
    return await get_annual_month_days(update, context, 4)


async def get_annual_month_5(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение дней на вахте для мая."""
    return await get_annual_month_days(update, context, 5)


async def get_annual_month_6(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение дней на вахте для июня."""
    return await get_annual_month_days(update, context, 6)


async def get_annual_month_7(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение дней на вахте для июля."""
    return await get_annual_month_days(update, context, 7)


async def get_annual_month_8(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение дней на вахте для августа."""
    return await get_annual_month_days(update, context, 8)


async def get_annual_month_9(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение дней на вахте для сентября."""
    return await get_annual_month_days(update, context, 9)


async def get_annual_month_10(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение дней на вахте для октября."""
    return await get_annual_month_days(update, context, 10)


async def get_annual_month_11(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение дней на вахте для ноября."""
    return await get_annual_month_days(update, context, 11)


async def get_annual_month_12(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение дней на вахте для декабря."""
    return await get_annual_month_days(update, context, 12)


async def get_annual_regional(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение региональной надбавки для 13-й зарплаты."""
    try:
        text = update.message.text.strip()
        value = Decimal(text.replace(",", "."))
        if value < 0 or value > 100:
            await update.message.reply_text(
                "❌ Процент должен быть от 0 до 100. Попробуйте ещё раз:"
            )
            return ANNUAL_REGIONAL
        context.user_data["annual_regional"] = value
    except (ValueError, InvalidOperation):
        await update.message.reply_text(
            "❌ Неверный формат. Введите число (например: 60 или 0):"
        )
        return ANNUAL_REGIONAL
    
    await update.message.reply_text(
        "❄️ Введите северную надбавку в процентах (0-100):"
    )
    return ANNUAL_NORTHERN


async def get_annual_northern(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение северной надбавки для 13-й зарплаты."""
    try:
        text = update.message.text.strip()
        value = Decimal(text.replace(",", "."))
        if value < 0 or value > 100:
            await update.message.reply_text(
                "❌ Процент должен быть от 0 до 100. Попробуйте ещё раз:"
            )
            return ANNUAL_NORTHERN
        context.user_data["annual_northern"] = value
    except (ValueError, InvalidOperation):
        await update.message.reply_text(
            "❌ Неверный формат. Введите число (например: 50 или 0):"
        )
        return ANNUAL_NORTHERN
    
    # Формируем сводку для подтверждения
    summary = "📋 Проверьте введённые данные для расчёта 13-й зарплаты:\n\n"
    summary += f"💰 Часовая ставка: {context.user_data['annual_hourly_rate']:.2f} ₽/час\n"
    summary += f"📅 Месяцев в компании за год: {context.user_data['annual_months']:.0f}\n"
    
    bonus_rate = context.user_data.get("annual_bonus_rate") or Decimal("33")
    summary += f"📈 Средний % ежемесячной премии: {bonus_rate:.1f}%\n"
    
    target_bonus = context.user_data.get("annual_target_bonus_rate")
    if target_bonus:
        summary += f"🎯 Целевой % годового вознаграждения: {target_bonus:.2f}%\n"
    
    kpi = context.user_data.get("annual_kpi") or Decimal("1.0")
    summary += f"📊 Коэффициент выполнения (KPI): {kpi:.2f}\n"
    
    correction = context.user_data.get("annual_correction_coefficient") or Decimal("1.0")
    summary += f"⚖️ Корректирующий коэффициент: {correction:.2f}\n\n"
    
    # Добавляем данные по месяцам
    summary += "📅 Дни на вахте по месяцам:\n"
    monthly_days = context.user_data.get("annual_monthly_days", {})
    for month_num in range(1, 13):
        days = monthly_days.get(month_num, Decimal("0"))
        summary += f"{MONTH_NAMES[month_num]}: {days:.0f} дн.\n"
    
    summary += "\n"
    
    regional = context.user_data.get("annual_regional") or Decimal("0")
    summary += f"📍 Региональная надбавка: {regional:.1f}%\n"
    
    northern = context.user_data.get("annual_northern") or Decimal("0")
    summary += f"❄️ Северная надбавка: {northern:.1f}%\n\n"
    summary += "Нажмите 'Рассчитать' для выполнения расчёта или 'Отмена' для выхода:"
    
    await update.message.reply_text(
        summary,
        reply_markup=get_salary_confirm_keyboard()
    )
    return ANNUAL_CONFIRM


async def confirm_annual_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждение и расчёт 13-й зарплаты."""
    user = update.effective_user
    query = update.callback_query
    
    if query:
        await query.answer()
    
    try:
        # Формируем словарь с днями по месяцам
        monthly_days = {}
        for month_num in range(1, 13):
            monthly_days[month_num] = context.user_data.get("annual_monthly_days", {}).get(month_num, Decimal("0"))
        
        # Выполняем расчёт
        calculation = calculate_annual_bonus(
            hourly_rate=context.user_data["annual_hourly_rate"],
            months_in_company=context.user_data["annual_months"],
            monthly_days=monthly_days,
            monthly_bonus_rate=context.user_data.get("annual_bonus_rate"),
            target_annual_bonus_rate=context.user_data.get("annual_target_bonus_rate"),
            kpi_coefficient=context.user_data.get("annual_kpi"),
            correction_coefficient=context.user_data.get("annual_correction_coefficient"),
            regional_allowance_rate=context.user_data.get("annual_regional"),
            northern_allowance_rate=context.user_data.get("annual_northern")
        )
        
        # Форматируем отчёт
        report = format_annual_bonus_report(calculation)
        
        message = query.message if query else update.message
        await message.reply_text(
            report,
            reply_markup=get_main_keyboard()
        )
        
        # Очищаем данные диалога
        context.user_data.clear()
        return ConversationHandler.END
        
    except AnnualBonusCalculationError as e:
        message = query.message if query else update.message
        await message.reply_text(
            f"❌ Ошибка расчёта: {e}\n\n"
            "Попробуйте начать заново через меню.",
            reply_markup=get_main_keyboard()
        )
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка при расчёте 13-й зарплаты для user_id={user.id}: {e}", exc_info=True)
        message = query.message if query else update.message
        await message.reply_text(
            "❌ Произошла ошибка при расчёте 13-й зарплаты.\n"
            "Попробуйте позже или обратитесь к администратору.",
            reply_markup=get_main_keyboard()
        )
        context.user_data.clear()
        return ConversationHandler.END


async def cancel_annual_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена расчёта 13-й зарплаты."""
    query = update.callback_query
    if query:
        await query.answer()
    
    context.user_data.clear()
    message = query.message if query else update.message
    await message.reply_text(
        "❌ Расчёт 13-й зарплаты отменён.",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на inline кнопки."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    # Игнорируем кнопки, которые обрабатываются ConversationHandler
    if data in ["salary", "annual_bonus", "skip", "confirm", "cancel"]:
        return
    
    if data == "weather":
        # Показываем подменю погоды
        await query.edit_message_text(
            "🌤️ Выберите тип прогноза погоды:",
            reply_markup=get_weather_menu_keyboard()
        )
    elif data == "weather_today":
        # Получаем погоду на сегодня
        try:
            await query.answer("Загружаю погоду...")
            weather_data = await get_weather()
            
            if weather_data:
                report = format_weather_report(weather_data)
                await query.edit_message_text(
                    report,
                    reply_markup=get_back_to_main_keyboard()
                )
                logger.info(f"Пользователь {query.from_user.id} запросил погоду на сегодня через кнопку")
            else:
                await query.edit_message_text(
                    "❌ Не удалось получить данные о погоде.\n"
                    "Попробуйте позже.",
                    reply_markup=get_back_to_main_keyboard()
                )
        except Exception as e:
            await query.edit_message_text(
                "❌ Произошла ошибка при получении погоды.",
                reply_markup=get_back_to_main_keyboard()
            )
            logger.error(f"Ошибка при получении погоды через кнопку: {e}")
    elif data == "weather_7days":
        # Погода на 7 дней
        try:
            await query.answer("Загружаю прогноз на 7 дней...")
            forecast_data = await get_7_day_forecast()
            
            if forecast_data:
                report = format_7_day_forecast_report(forecast_data)
                await query.edit_message_text(
                    report,
                    reply_markup=get_back_to_main_keyboard()
                )
                logger.info(f"Пользователь {query.from_user.id} запросил прогноз на 7 дней через кнопку")
            else:
                await query.edit_message_text(
                    "❌ Не удалось получить прогноз погоды на 7 дней.\n"
                    "Попробуйте позже.",
                    reply_markup=get_back_to_main_keyboard()
                )
        except Exception as e:
            await query.edit_message_text(
                "❌ Произошла ошибка при получении прогноза погоды.",
                reply_markup=get_back_to_main_keyboard()
            )
            logger.error(f"Ошибка при получении прогноза на 7 дней через кнопку: {e}")
    elif data == "flight_probability":
        # Вероятность вылета
        try:
            await query.answer("Анализирую погоду для вылета...")
            forecast_data = await get_flight_forecast()
            
            if forecast_data:
                report = format_flight_forecast_report(forecast_data)
                await query.edit_message_text(
                    report,
                    reply_markup=get_back_to_main_keyboard()
                )
                logger.info(f"Пользователь {query.from_user.id} запросил анализ вероятности вылета через кнопку")
            else:
                await query.edit_message_text(
                    "❌ Не удалось получить анализ вероятности вылета.\n"
                    "Попробуйте позже.",
                    reply_markup=get_back_to_main_keyboard()
                )
        except Exception as e:
            await query.edit_message_text(
                "❌ Произошла ошибка при анализе вероятности вылета.",
                reply_markup=get_back_to_main_keyboard()
            )
            logger.error(f"Ошибка при получении анализа вероятности вылета через кнопку: {e}")
    elif data == "money_calc":
        # Показываем подменю расчета денег
        await query.edit_message_text(
            "💰 Выберите тип расчёта:",
            reply_markup=get_money_calc_keyboard()
        )
    elif data == "back_to_main":
        # Возврат к главному меню
        await query.edit_message_text(
            "Главное меню:",
            reply_markup=get_main_keyboard()
        )
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
    # Проверяем как telegram ошибки, так и httpx ошибки
    is_network_error = isinstance(error, (NetworkError, TimedOut))
    
    # Проверяем httpx ошибки (ConnectError, ReadTimeout и т.д.)
    if not is_network_error:
        error_type_name = type(error).__name__
        error_module = getattr(error, '__module__', '')
        is_network_error = (
            'ConnectError' in error_type_name or
            'ReadTimeout' in error_type_name or
            'ConnectTimeout' in error_type_name or
            'httpx' in error_module
        )
    
    if is_network_error:
        logger.warning(f"Сетевая ошибка при обработке обновления: {error}")
        
        # Пытаемся отправить сообщение пользователю с просьбой повторить запрос
        if isinstance(update, Update) and update.effective_message:
            # Используем безопасную отправку с повторной попыткой
            for attempt in range(3):
                try:
                    await update.effective_message.reply_text(
                        "⚠️ Произошла временная сетевая ошибка.\n\n"
                        "Пожалуйста, повторите ваш запрос через несколько секунд."
                    )
                    break
                except Exception as send_error:
                    if attempt < 2:
                        await asyncio.sleep(1)  # Ждём 1 секунду перед повторной попыткой
                    else:
                        logger.error(f"Не удалось отправить сообщение о сетевой ошибке после 3 попыток: {send_error}")
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
            HOURLY_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_hourly_rate)],
            DAYS_WORKED: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_days_worked)],
            NIGHT_HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_night_hours)],
            IDLE_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_idle_days)],
            TRAVEL_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_travel_days)],
            HOLIDAY_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_holiday_days)],
            ADDITIONAL_PAYMENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_additional_payments)],
            REGIONAL_ALLOWANCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_regional_allowance)],
            NORTHERN_ALLOWANCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_northern_allowance)],
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
    
    # Диалог расчёта 13-й зарплаты
    annual_bonus_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(annual_bonus_start, pattern="^annual_bonus$")
        ],
        states={
            ANNUAL_HOURLY_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_annual_hourly_rate)],
            ANNUAL_MONTHS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_annual_months)],
            ANNUAL_BONUS_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_annual_bonus_rate)],
            ANNUAL_TARGET_BONUS_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_annual_target_bonus_rate)],
            ANNUAL_KPI: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_annual_kpi)],
            ANNUAL_CORRECTION_COEFFICIENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_annual_correction_coefficient)],
            ANNUAL_MONTH_1: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_annual_month_1)],
            ANNUAL_MONTH_2: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_annual_month_2)],
            ANNUAL_MONTH_3: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_annual_month_3)],
            ANNUAL_MONTH_4: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_annual_month_4)],
            ANNUAL_MONTH_5: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_annual_month_5)],
            ANNUAL_MONTH_6: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_annual_month_6)],
            ANNUAL_MONTH_7: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_annual_month_7)],
            ANNUAL_MONTH_8: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_annual_month_8)],
            ANNUAL_MONTH_9: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_annual_month_9)],
            ANNUAL_MONTH_10: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_annual_month_10)],
            ANNUAL_MONTH_11: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_annual_month_11)],
            ANNUAL_MONTH_12: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_annual_month_12)],
            ANNUAL_REGIONAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_annual_regional)],
            ANNUAL_NORTHERN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_annual_northern)],
            ANNUAL_CONFIRM: [
                CallbackQueryHandler(confirm_annual_bonus, pattern="^confirm$"),
                CallbackQueryHandler(cancel_annual_bonus, pattern="^cancel$")
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_annual_bonus),
            CommandHandler("start", cancel_annual_bonus),
        ],
    )
    application.add_handler(annual_bonus_conv_handler)
    
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

