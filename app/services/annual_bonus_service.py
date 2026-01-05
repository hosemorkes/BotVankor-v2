"""
Сервис для расчёта 13-й зарплаты (годового вознаграждения).
Логика расчёта соответствует Excel формуле.
"""

from typing import Optional
from decimal import Decimal, InvalidOperation


class AnnualBonusCalculationError(Exception):
    """Ошибка при расчёте 13-й зарплаты."""
    pass


# Константы из Excel
HOURS_PER_DAY = Decimal("11")  # Часов в рабочем дне
DEFAULT_MONTHLY_BONUS_RATE = Decimal("33")  # E103 - Средний % ежемесячной премии за год (по умолчанию)
DEFAULT_KPI_COEFFICIENT = Decimal("1.0")  # E105 - Коэффициент выполнения (KPI) (по умолчанию)
DEFAULT_CORRECTION_COEFFICIENT = Decimal("1.0")  # E106 - Корректирующий коэффициент (по умолчанию)
TAX_RATE = Decimal("13")  # C126 - Налог в процентах
MONTHS_IN_YEAR = Decimal("12")  # Количество месяцев в году


def validate_annual_bonus_inputs(
    hourly_rate: Decimal,
    months_in_company: Decimal,
    monthly_days: dict[int, Decimal],
    monthly_bonus_rate: Optional[Decimal] = None,
    target_annual_bonus_rate: Optional[Decimal] = None,
    kpi_coefficient: Optional[Decimal] = None,
    correction_coefficient: Optional[Decimal] = None,
    regional_allowance_rate: Optional[Decimal] = None,
    northern_allowance_rate: Optional[Decimal] = None
) -> None:
    """
    Валидирует входные данные для расчёта 13-й зарплаты.
    
    Args:
        hourly_rate: Часовая ставка (E101)
        months_in_company: Кол-во месяцев в компании за год (E102, 1-12)
        monthly_days: Словарь с днями на вахте по месяцам {1: дни_января, 2: дни_февраля, ...}
        monthly_bonus_rate: Средний % ежемесячной премии за год (E103, опционально)
        target_annual_bonus_rate: Целевой % годового вознаграждения по должности (E104, опционально)
        kpi_coefficient: Коэффициент выполнения (KPI) (E105, опционально)
        correction_coefficient: Корректирующий коэффициент (E106, опционально)
        regional_allowance_rate: Региональная надбавка в процентах (C122, опционально)
        northern_allowance_rate: Северная надбавка в процентах (C123, опционально)
    
    Raises:
        AnnualBonusCalculationError: При невалидных данных
    """
    if hourly_rate <= 0:
        raise AnnualBonusCalculationError("Часовая ставка должна быть больше нуля")
    
    if months_in_company < 1 or months_in_company > 12:
        raise AnnualBonusCalculationError("Количество месяцев в компании должно быть от 1 до 12")
    
    if len(monthly_days) != 12:
        raise AnnualBonusCalculationError("Должно быть указано количество дней для всех 12 месяцев")
    
    for month_num, days in monthly_days.items():
        if month_num < 1 or month_num > 12:
            raise AnnualBonusCalculationError(f"Номер месяца должен быть от 1 до 12, получен: {month_num}")
        if days < 0:
            raise AnnualBonusCalculationError(f"Количество дней в месяце {month_num} не может быть отрицательным")
        if days > 31:
            raise AnnualBonusCalculationError(f"Количество дней в месяце {month_num} не может быть больше 31")
    
    if monthly_bonus_rate is not None and (monthly_bonus_rate < 0 or monthly_bonus_rate > 100):
        raise AnnualBonusCalculationError("Процент ежемесячной премии должен быть от 0 до 100%")
    
    if target_annual_bonus_rate is not None and (target_annual_bonus_rate < 0 or target_annual_bonus_rate > 100):
        raise AnnualBonusCalculationError("Целевой % годового вознаграждения должен быть от 0 до 100%")
    
    if kpi_coefficient is not None and kpi_coefficient < 0:
        raise AnnualBonusCalculationError("Коэффициент выполнения (KPI) не может быть отрицательным")
    
    if correction_coefficient is not None and correction_coefficient < 0:
        raise AnnualBonusCalculationError("Корректирующий коэффициент не может быть отрицательным")
    
    if regional_allowance_rate is not None:
        if regional_allowance_rate < 0 or regional_allowance_rate > 100:
            raise AnnualBonusCalculationError("Региональная надбавка должна быть от 0 до 100%")
    
    if northern_allowance_rate is not None:
        if northern_allowance_rate < 0 or northern_allowance_rate > 100:
            raise AnnualBonusCalculationError("Северная надбавка должна быть от 0 до 100%")


def calculate_annual_bonus(
    hourly_rate: Decimal,
    months_in_company: Decimal,
    monthly_days: dict[int, Decimal],
    monthly_bonus_rate: Optional[Decimal] = None,
    target_annual_bonus_rate: Optional[Decimal] = None,
    kpi_coefficient: Optional[Decimal] = None,
    correction_coefficient: Optional[Decimal] = None,
    regional_allowance_rate: Optional[Decimal] = None,
    northern_allowance_rate: Optional[Decimal] = None
) -> dict[str, Decimal]:
    """
    Рассчитывает 13-ю зарплату (годовое вознаграждение) согласно Excel формуле.
    
    Порядок расчёта:
    1. Для каждого месяца i (1…12):
       - H_i = M_i * 11 (часы месяца)
       - Z_i = H_i * E101 (оплата по окладу)
       - P_i = Z_i * (E103 / 100) (ежемесячная премия)
       - B_i = Z_i + P_i (база месяца для 13-й)
    2. E201: Среднемесячная база для 13-й = (B_1 + B_2 + ... + B_12) / E102
    3. E202: Годовая база для 13-й = E201 * 12
    4. E210: Годовое вознаграждение (без РК и СН) = E202 * (E104 / 100) * E105 * E106 * (E102 / 12)
    5. E211: Региональная надбавка на 13-ю = E210 * (C122 / 100)
    6. E212: Северная надбавка на 13-ю = E210 * (C123 / 100)
    7. E213: Всего начислено (13-я) = E210 + E211 + E212
    8. E214: Налог (13%) = E213 * (C126 / 100)
    9. E215: 13-я зарплата на руки = E213 - E214
    
    Args:
        hourly_rate: Часовая ставка (E101)
        months_in_company: Кол-во месяцев в компании за год (E102, 1-12)
        monthly_days: Словарь с днями на вахте по месяцам {1: дни_января, 2: дни_февраля, ..., 12: дни_декабря}
        monthly_bonus_rate: Средний % ежемесячной премии за год (E103, опционально, по умолчанию 33)
        target_annual_bonus_rate: Целевой % годового вознаграждения по должности (E104, опционально)
        kpi_coefficient: Коэффициент выполнения (KPI) (E105, опционально, по умолчанию 1.0)
        correction_coefficient: Корректирующий коэффициент (E106, опционально, по умолчанию 1.0)
        regional_allowance_rate: Региональная надбавка в процентах (C122, опционально)
        northern_allowance_rate: Северная надбавка в процентах (C123, опционально)
    
    Returns:
        Словарь с расчётами:
        - hourly_rate: Часовая ставка (E101)
        - months_in_company: Кол-во месяцев в компании (E102)
        - monthly_bonus_rate: Средний % ежемесячной премии (E103)
        - target_annual_bonus_rate: Целевой % годового вознаграждения (E104)
        - kpi_coefficient: Коэффициент выполнения (KPI) (E105)
        - correction_coefficient: Корректирующий коэффициент (E106)
        - monthly_data: Словарь с данными по каждому месяцу {1: {hours, salary, bonus, base}, ...}
        - average_monthly_base: Среднемесячная база для 13-й (E201)
        - annual_base: Годовая база для 13-й (E202)
        - annual_reward_without_allowances: Годовое вознаграждение без РК и СН (E210)
        - regional_allowance_rate: Региональная надбавка в % (C122)
        - regional_allowance: Региональная надбавка на 13-ю (E211)
        - northern_allowance_rate: Северная надбавка в % (C123)
        - northern_allowance: Северная надбавка на 13-ю (E212)
        - total_accrued: Всего начислено (13-я) (E213)
        - tax: Налог (13%) (E214)
        - net: 13-я зарплата на руки (E215)
    
    Raises:
        AnnualBonusCalculationError: При невалидных входных данных
    """
    # Инициализация опциональных значений
    monthly_bonus_rate = monthly_bonus_rate or DEFAULT_MONTHLY_BONUS_RATE
    kpi_coefficient = kpi_coefficient or DEFAULT_KPI_COEFFICIENT
    correction_coefficient = correction_coefficient or DEFAULT_CORRECTION_COEFFICIENT
    regional_allowance_rate = regional_allowance_rate or Decimal("0")
    northern_allowance_rate = northern_allowance_rate or Decimal("0")
    
    # Валидация входных данных
    validate_annual_bonus_inputs(
        hourly_rate=hourly_rate,
        months_in_company=months_in_company,
        monthly_days=monthly_days,
        monthly_bonus_rate=monthly_bonus_rate,
        target_annual_bonus_rate=target_annual_bonus_rate,
        kpi_coefficient=kpi_coefficient,
        correction_coefficient=correction_coefficient,
        regional_allowance_rate=regional_allowance_rate,
        northern_allowance_rate=northern_allowance_rate
    )
    
    if target_annual_bonus_rate is None:
        raise AnnualBonusCalculationError("Целевой % годового вознаграждения по должности (E104) обязателен для расчёта")
    
    # Расчёт базы КАЖДОГО месяца
    monthly_data = {}
    total_base = Decimal("0")
    
    month_names = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
        5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
        9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
    }
    
    for month_num in range(1, 13):
        days = monthly_days.get(month_num, Decimal("0"))
        
        # H_i = M_i * 11
        hours = days * HOURS_PER_DAY
        
        # Z_i = H_i * E101
        salary = hours * hourly_rate
        
        # P_i = Z_i * (E103 / 100)
        bonus = salary * (monthly_bonus_rate / Decimal("100"))
        
        # B_i = Z_i + P_i
        base = salary + bonus
        
        monthly_data[month_num] = {
            "name": month_names[month_num],
            "days": days,
            "hours": hours,
            "salary": salary,
            "bonus": bonus,
            "base": base
        }
        
        total_base += base
    
    # E201 = Среднемесячная база для 13-й = (B_1 + B_2 + ... + B_12) / E102
    average_monthly_base = total_base / months_in_company
    
    # E202 = Годовая база для 13-й = E201 * 12
    annual_base = average_monthly_base * MONTHS_IN_YEAR
    
    # E210 = Годовое вознаграждение (без РК и СН) = E202 * (E104 / 100) * E105 * E106 * (E102 / 12)
    annual_reward_without_allowances = (
        annual_base * 
        (target_annual_bonus_rate / Decimal("100")) * 
        kpi_coefficient * 
        correction_coefficient * 
        (months_in_company / MONTHS_IN_YEAR)
    )
    
    # E211 = Региональная надбавка на 13-ю = E210 * (C122 / 100)
    regional_allowance = annual_reward_without_allowances * (regional_allowance_rate / Decimal("100"))
    
    # E212 = Северная надбавка на 13-ю = E210 * (C123 / 100)
    northern_allowance = annual_reward_without_allowances * (northern_allowance_rate / Decimal("100"))
    
    # E213 = Всего начислено (13-я) = E210 + E211 + E212
    total_accrued = annual_reward_without_allowances + regional_allowance + northern_allowance
    
    # E214 = Налог (13%) = E213 * (C126 / 100)
    tax = total_accrued * (TAX_RATE / Decimal("100"))
    
    # E215 = 13-я зарплата на руки = E213 - E214
    net = total_accrued - tax
    
    return {
        "hourly_rate": hourly_rate,
        "months_in_company": months_in_company,
        "monthly_bonus_rate": monthly_bonus_rate,
        "target_annual_bonus_rate": target_annual_bonus_rate,
        "kpi_coefficient": kpi_coefficient,
        "correction_coefficient": correction_coefficient,
        "monthly_data": monthly_data,
        "average_monthly_base": average_monthly_base,
        "annual_base": annual_base,
        "annual_reward_without_allowances": annual_reward_without_allowances,
        "regional_allowance_rate": regional_allowance_rate,
        "regional_allowance": regional_allowance,
        "northern_allowance_rate": northern_allowance_rate,
        "northern_allowance": northern_allowance,
        "total_accrued": total_accrued,
        "tax": tax,
        "net": net,
    }


def format_annual_bonus_report(calculation: dict[str, Decimal]) -> str:
    """
    Форматирует отчёт о 13-й зарплате для вывода пользователю.
    
    Args:
        calculation: Результат расчёта из calculate_annual_bonus
    
    Returns:
        Отформатированная строка с отчётом
    """
    report = "🎁 Расчёт 13-й зарплаты (годовое вознаграждение):\n\n"
    
    # Основные параметры
    report += f"📊 Часовая ставка: {calculation['hourly_rate']:.2f} ₽/час\n"
    report += f"📅 Месяцев в компании за год: {calculation['months_in_company']:.0f}\n"
    report += f"📈 Средний % ежемесячной премии: {calculation['monthly_bonus_rate']:.1f}%\n"
    report += f"🎯 Целевой % годового вознаграждения: {calculation['target_annual_bonus_rate']:.2f}%\n"
    report += f"📊 Коэффициент выполнения (KPI): {calculation['kpi_coefficient']:.2f}\n"
    report += f"⚖️ Корректирующий коэффициент: {calculation['correction_coefficient']:.2f}\n\n"
    
    # Данные по месяцам (только месяцы с днями > 0)
    report += "📅 Данные по месяцам:\n"
    monthly_data = calculation['monthly_data']
    for month_num in range(1, 13):
        month_info = monthly_data[month_num]
        if month_info['days'] > 0:
            report += f"{month_info['name']}: {month_info['days']:.0f} дн. → "
            report += f"{month_info['hours']:.1f} ч → "
            report += f"{month_info['base']:.2f} ₽\n"
    
    report += "\n"
    
    # Среднемесячная и годовая база
    report += f"💰 Среднемесячная база для 13-й (E201): {calculation['average_monthly_base']:.2f} ₽\n"
    report += f"💰 Годовая база для 13-й (E202): {calculation['annual_base']:.2f} ₽\n\n"
    
    # Годовое вознаграждение
    report += "📊 Годовое вознаграждение:\n"
    report += f"💼 Годовое вознаграждение (без РК и СН) (E210): {calculation['annual_reward_without_allowances']:.2f} ₽\n"
    
    if calculation['regional_allowance_rate'] > 0:
        report += f"📍 Региональная надбавка ({calculation['regional_allowance_rate']:.1f}%) (E211): {calculation['regional_allowance']:.2f} ₽\n"
    
    if calculation['northern_allowance_rate'] > 0:
        report += f"❄️ Северная надбавка ({calculation['northern_allowance_rate']:.1f}%) (E212): {calculation['northern_allowance']:.2f} ₽\n"
    
    report += "\n"
    report += f"📊 Всего начислено (13-я) (E213): {calculation['total_accrued']:.2f} ₽\n"
    report += f"📉 Налог (13%) (E214): {calculation['tax']:.2f} ₽\n"
    report += f"✅ 13-я зарплата на руки (E215): {calculation['net']:.2f} ₽"
    
    return report
