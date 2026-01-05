"""
Сервис для расчёта зарплаты по вахтовому методу работы.
Логика расчёта соответствует Excel формуле.
"""

from typing import Optional
from decimal import Decimal, InvalidOperation


class SalaryCalculationError(Exception):
    """Ошибка при расчёте зарплаты."""
    pass


# Константы из Excel
MONTHLY_BONUS_RATE = Decimal("33")  # E1 - Премия месячная в процентах
NIGHT_SHIFT_RATE = Decimal("40")  # C4 - Доплата за ночных смен в процентах
STANDARD_HOURS_PER_MONTH = Decimal("164.5")  # E12 - 40 часовая неделя по табелю
TAX_RATE = Decimal("13")  # C26 - Налог в процентах
HOURS_PER_DAY = Decimal("11")  # Часов в рабочем дне
TRAVEL_HOURS_PER_DAY = Decimal("8")  # Часов в дне в пути
IDLE_RATE = Decimal("2") / Decimal("3")  # Коэффициент оплаты простоя (2/3)
SHIFT_METHOD_RATE = Decimal("740")  # Ставка за вахтовый метод (рублей за день)


def validate_salary_inputs(
    hourly_rate: Decimal,
    days_worked: Decimal,
    night_hours: Optional[Decimal] = None,
    idle_days: Optional[Decimal] = None,
    travel_days: Optional[Decimal] = None,
    holiday_days: Optional[Decimal] = None,
    additional_payments: Optional[Decimal] = None,
    regional_allowance_rate: Optional[Decimal] = None,
    northern_allowance_rate: Optional[Decimal] = None
) -> None:
    """
    Валидирует входные данные для расчёта зарплаты.
    
    Args:
        hourly_rate: Часовая ставка
        days_worked: Количество отработанных дней
        night_hours: Количество ночных смен (в часах)
        idle_days: Количество дней простоя
        travel_days: Дни в пути
        holiday_days: Количество праздников
        additional_payments: Премии и прочие доплаты
        regional_allowance_rate: Региональная надбавка в процентах (0-100)
        northern_allowance_rate: Северная надбавка в процентах (0-100)
    
    Raises:
        SalaryCalculationError: При невалидных данных
    """
    if hourly_rate <= 0:
        raise SalaryCalculationError("Часовая ставка должна быть больше нуля")
    
    if days_worked < 0:
        raise SalaryCalculationError("Количество отработанных дней не может быть отрицательным")
    
    if days_worked > 365:
        raise SalaryCalculationError("Количество отработанных дней превышает разумный максимум (365 дней)")
    
    if night_hours is not None and night_hours < 0:
        raise SalaryCalculationError("Количество ночных часов не может быть отрицательным")
    
    if idle_days is not None and idle_days < 0:
        raise SalaryCalculationError("Количество дней простоя не может быть отрицательным")
    
    if travel_days is not None and travel_days < 0:
        raise SalaryCalculationError("Количество дней в пути не может быть отрицательным")
    
    if holiday_days is not None and holiday_days < 0:
        raise SalaryCalculationError("Количество праздничных дней не может быть отрицательным")
    
    if additional_payments is not None and additional_payments < 0:
        raise SalaryCalculationError("Доплаты не могут быть отрицательными")
    
    if regional_allowance_rate is not None:
        if regional_allowance_rate < 0 or regional_allowance_rate > 100:
            raise SalaryCalculationError("Региональная надбавка должна быть от 0 до 100%")
    
    if northern_allowance_rate is not None:
        if northern_allowance_rate < 0 or northern_allowance_rate > 100:
            raise SalaryCalculationError("Северная надбавка должна быть от 0 до 100%")


def calculate_salary(
    hourly_rate: Decimal,
    days_worked: Decimal,
    night_hours: Optional[Decimal] = None,
    idle_days: Optional[Decimal] = None,
    travel_days: Optional[Decimal] = None,
    holiday_days: Optional[Decimal] = None,
    additional_payments: Optional[Decimal] = None,
    regional_allowance_rate: Optional[Decimal] = None,
    northern_allowance_rate: Optional[Decimal] = None
) -> dict[str, Decimal]:
    """
    Рассчитывает зарплату по вахтовому методу работы согласно Excel формуле.
    
    Порядок расчёта:
    1. Часы по табелю = дни * 11
    2. Оплата по окладу = часы по табелю * часовая ставка
    3. Доплата за праздничные дни = праздники * ставка * 11
    4. Оплата простоя = дни простоя * 11 * ставка * (2/3)
    5. Доплата за дни в пути = дни в пути * ставка * 8
    6. Доплата за вахтовый метод = (дни + дни в пути) * 740
    7. Доплата за ночные = ночные часы * ставка * 40%
    8. Премия месячная = (оклад + простой + ночные) * 33%
    9. Региональная надбавка = (оклад + праздники + ночные + премия + простой) * региональный %
    10. Северная надбавка = (оклад + праздники + ночные + премия + простой) * северный %
    11. Всего начислено = сумма всех начислений + доплаты
    12. Налог = (всего - вахтовый метод - дни в пути) * 13%
    13. ЗП к выплате = всего - налог
    
    Args:
        hourly_rate: Часовая ставка (E13)
        days_worked: Количество отработанных дней (E5)
        night_hours: Количество ночных смен в часах (E6, опционально)
        idle_days: Количество дней простоя (E7, опционально)
        travel_days: Дни в пути (E8, опционально)
        holiday_days: Количество праздников (E9, опционально)
        additional_payments: Премии и прочие доплаты (E10, опционально)
        regional_allowance_rate: Региональная надбавка в процентах (C22, опционально)
        northern_allowance_rate: Северная надбавка в процентах (C23, опционально)
    
    Returns:
        Словарь с расчётами:
        - hourly_rate: Часовая ставка
        - days_worked: Отработанные дни
        - hours_by_timesheet: Часы по табелю
        - salary_by_position: Оплата по окладу
        - holiday_payment: Доплата за праздничные дни
        - idle_payment: Оплата простоя
        - travel_payment: Доплата за дни в пути
        - shift_method_payment: Доплата за вахтовый метод
        - night_shift_payment: Доплата за ночные
        - monthly_bonus: Премия месячная
        - regional_allowance: Региональная надбавка
        - northern_allowance: Северная надбавка
        - additional_payments: Премии и прочие доплаты
        - total_accrued: Всего начислено
        - tax: Налог
        - net: ЗП к выплате
    
    Raises:
        SalaryCalculationError: При невалидных входных данных
    """
    # Валидация входных данных
    validate_salary_inputs(
        hourly_rate=hourly_rate,
        days_worked=days_worked,
        night_hours=night_hours,
        idle_days=idle_days,
        travel_days=travel_days,
        holiday_days=holiday_days,
        additional_payments=additional_payments,
        regional_allowance_rate=regional_allowance_rate,
        northern_allowance_rate=northern_allowance_rate
    )
    
    # Инициализация опциональных значений
    night_hours = night_hours or Decimal("0")
    idle_days = idle_days or Decimal("0")
    travel_days = travel_days or Decimal("0")
    holiday_days = holiday_days or Decimal("0")
    additional_payments = additional_payments or Decimal("0")
    regional_allowance_rate = regional_allowance_rate or Decimal("0")
    northern_allowance_rate = northern_allowance_rate or Decimal("0")
    
    # E11 = Часы по табелю = дни * 11
    hours_by_timesheet = days_worked * HOURS_PER_DAY
    
    # E15 = Оплата по окладу = часы по табелю * часовая ставка
    salary_by_position = hours_by_timesheet * hourly_rate
    
    # E16 = Доплата за праздничные дни = праздники * ставка * 11
    holiday_payment = holiday_days * hourly_rate * HOURS_PER_DAY
    
    # E17 = Оплата простоя = дни простоя * 11 * ставка * (2/3)
    idle_payment = idle_days * HOURS_PER_DAY * hourly_rate * IDLE_RATE
    
    # E18 = Доплата за дни в пути = дни в пути * ставка * 8
    travel_payment = travel_days * hourly_rate * TRAVEL_HOURS_PER_DAY
    
    # E19 = Доплата за вахтовый метод = (дни + дни в пути) * 740
    shift_method_payment = (days_worked + travel_days) * SHIFT_METHOD_RATE
    
    # E20 = Доплата за ночные = ночные часы * ставка * (40 / 100)
    night_shift_payment = night_hours * hourly_rate * (NIGHT_SHIFT_RATE / Decimal("100"))
    
    # E21 = Премия месячная = (оклад + простой + ночные) * 33%
    monthly_bonus = (salary_by_position + idle_payment + night_shift_payment) * (MONTHLY_BONUS_RATE / Decimal("100"))
    
    # E22 = Региональная надбавка = (оклад + праздники + ночные + премия + простой) * региональный %
    regional_allowance = (salary_by_position + holiday_payment + night_shift_payment + monthly_bonus + idle_payment) * (regional_allowance_rate / Decimal("100"))
    
    # E23 = Северная надбавка = (оклад + праздники + ночные + премия + простой) * северный %
    northern_allowance = (salary_by_position + holiday_payment + night_shift_payment + monthly_bonus + idle_payment) * (northern_allowance_rate / Decimal("100"))
    
    # E25 = Всего начислено = СУММ(E15:E23) + E10
    total_accrued = (
        salary_by_position +
        holiday_payment +
        idle_payment +
        travel_payment +
        shift_method_payment +
        night_shift_payment +
        monthly_bonus +
        regional_allowance +
        northern_allowance +
        additional_payments
    )
    
    # E26 = Налог = (всего - вахтовый метод - дни в пути) * 13%
    taxable_base = total_accrued - shift_method_payment - travel_payment
    tax = taxable_base * (TAX_RATE / Decimal("100"))
    
    # E27 = ЗП = всего - налог
    net = total_accrued - tax
    
    return {
        "hourly_rate": hourly_rate,
        "days_worked": days_worked,
        "night_hours": night_hours,
        "idle_days": idle_days,
        "travel_days": travel_days,
        "holiday_days": holiday_days,
        "hours_by_timesheet": hours_by_timesheet,
        "salary_by_position": salary_by_position,
        "holiday_payment": holiday_payment,
        "idle_payment": idle_payment,
        "travel_payment": travel_payment,
        "shift_method_payment": shift_method_payment,
        "night_shift_payment": night_shift_payment,
        "monthly_bonus": monthly_bonus,
        "regional_allowance_rate": regional_allowance_rate,
        "regional_allowance": regional_allowance,
        "northern_allowance_rate": northern_allowance_rate,
        "northern_allowance": northern_allowance,
        "additional_payments": additional_payments,
        "total_accrued": total_accrued,
        "taxable_base": taxable_base,
        "tax": tax,
        "net": net,
    }


def format_salary_report(calculation: dict[str, Decimal]) -> str:
    """
    Форматирует отчёт о зарплате для вывода пользователю.
    
    Args:
        calculation: Результат расчёта из calculate_salary
    
    Returns:
        Отформатированная строка с отчётом
    """
    report = "💰 Расчёт зарплаты (вахтовый метод):\n\n"
    
    # Основные параметры
    report += f"📊 Часовая ставка: {calculation['hourly_rate']:.2f} ₽/час\n"
    report += f"📅 Отработано дней: {calculation['days_worked']:.0f}\n"
    
    # Выводим количество простоя только если оно больше 0
    if calculation['idle_days'] > 0:
        report += f"⏸️ Количество простоя: {calculation['idle_days']:.0f} дн.\n"
    
    report += f"⏰ Часов по табелю: {calculation['hours_by_timesheet']:.1f}\n\n"
    
    # Начисления
    report += "📈 Начисления:\n"
    report += f"💵 Оплата по окладу: {calculation['salary_by_position']:.2f} ₽\n"
    
    if calculation['holiday_days'] > 0:
        report += f"🎉 Доплата за праздники ({calculation['holiday_days']:.0f} дн.): {calculation['holiday_payment']:.2f} ₽\n"
    
    if calculation['idle_days'] > 0:
        report += f"⏸️ Оплата простоя ({calculation['idle_days']:.0f} дн.): {calculation['idle_payment']:.2f} ₽\n"
    
    if calculation['travel_days'] > 0:
        report += f"🚗 Доплата за дни в пути ({calculation['travel_days']:.0f} дн.): {calculation['travel_payment']:.2f} ₽\n"
    
    report += f"🏕️ Доплата за вахтовый метод: {calculation['shift_method_payment']:.2f} ₽\n"
    
    if calculation['night_hours'] > 0:
        report += f"🌙 Доплата за ночные ({calculation['night_hours']:.1f} ч): {calculation['night_shift_payment']:.2f} ₽\n"
    
    if calculation['monthly_bonus'] > 0:
        report += f"🎁 Премия месячная (33%): {calculation['monthly_bonus']:.2f} ₽\n"
    
    if calculation['regional_allowance_rate'] > 0:
        report += f"📍 Региональная надбавка ({calculation['regional_allowance_rate']:.1f}%): {calculation['regional_allowance']:.2f} ₽\n"
    
    if calculation['northern_allowance_rate'] > 0:
        report += f"❄️ Северная надбавка ({calculation['northern_allowance_rate']:.1f}%): {calculation['northern_allowance']:.2f} ₽\n"
    
    if calculation['additional_payments'] > 0:
        report += f"➕ Прочие доплаты: {calculation['additional_payments']:.2f} ₽\n"
    
    report += "\n"
    report += f"📊 Всего начислено: {calculation['total_accrued']:.2f} ₽\n"
    report += f"📉 Налог (13%): {calculation['tax']:.2f} ₽\n"
    report += f"✅ ЗП к выплате: {calculation['net']:.2f} ₽"
    
    return report
