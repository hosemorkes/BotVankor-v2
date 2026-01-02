"""
Сервис для расчёта зарплаты с учётом северных надбавок, районного коэффициента и переработок.
"""

from typing import Optional
from decimal import Decimal, InvalidOperation


class SalaryCalculationError(Exception):
    """Ошибка при расчёте зарплаты."""
    pass


def validate_salary_inputs(
    base_salary: Decimal,
    hours_worked: Decimal,
    northern_allowance_rate: Optional[Decimal] = None,
    district_coefficient: Optional[Decimal] = None,
    overtime_hours: Optional[Decimal] = None,
    bonus: Optional[Decimal] = None
) -> None:
    """
    Валидирует входные данные для расчёта зарплаты.
    
    Args:
        base_salary: Базовая ставка за час или оклад за месяц
        hours_worked: Отработанные часы
        northern_allowance_rate: Процент северной надбавки (0-100)
        district_coefficient: Районный коэффициент (обычно 1.0-2.0)
        overtime_hours: Переработанные часы
        bonus: Бонус
    
    Raises:
        SalaryCalculationError: При невалидных данных
    """
    if base_salary <= 0:
        raise SalaryCalculationError("Базовая ставка должна быть больше нуля")
    
    if hours_worked < 0:
        raise SalaryCalculationError("Отработанные часы не могут быть отрицательными")
    
    if hours_worked > 744:  # Максимум часов в месяце (31 день * 24 часа)
        raise SalaryCalculationError("Отработанные часы превышают разумный максимум")
    
    if northern_allowance_rate is not None:
        if northern_allowance_rate < 0 or northern_allowance_rate > 100:
            raise SalaryCalculationError("Северная надбавка должна быть от 0 до 100%")
    
    if district_coefficient is not None:
        if district_coefficient < 1.0 or district_coefficient > 3.0:
            raise SalaryCalculationError("Районный коэффициент должен быть от 1.0 до 3.0")
    
    if overtime_hours is not None:
        if overtime_hours < 0:
            raise SalaryCalculationError("Переработанные часы не могут быть отрицательными")
        if overtime_hours > hours_worked:
            raise SalaryCalculationError("Переработанные часы не могут превышать отработанные")
    
    if bonus is not None and bonus < 0:
        raise SalaryCalculationError("Бонус не может быть отрицательным")


def calculate_salary(
    base_salary: Decimal,
    hours_worked: Decimal,
    bonus: Optional[Decimal] = None,
    northern_allowance_rate: Optional[Decimal] = None,
    district_coefficient: Optional[Decimal] = None,
    overtime_hours: Optional[Decimal] = None,
    overtime_multiplier: Decimal = Decimal("1.5"),  # Стандартный коэффициент для переработок
    tax_rate: Decimal = Decimal("0.13")
) -> dict[str, Decimal]:
    """
    Рассчитывает зарплату с учётом отработанных часов, северных надбавок,
    районного коэффициента, переработок, бонусов и налогов.
    
    Порядок расчёта:
    1. Базовый оклад (ставка * часы)
    2. Применение районного коэффициента
    3. Добавление северных надбавок (от оклада с коэффициентом)
    4. Добавление переработок (сверхурочные часы * повышенная ставка)
    5. Добавление бонуса
    6. Вычет налога
    7. Итоговая сумма к выплате
    
    Args:
        base_salary: Базовая ставка за час или оклад за месяц
        hours_worked: Отработанные часы (нормальные)
        bonus: Бонус (опционально)
        northern_allowance_rate: Процент северной надбавки (0-100, опционально)
        district_coefficient: Районный коэффициент (опционально, по умолчанию 1.0)
        overtime_hours: Переработанные часы (опционально)
        overtime_multiplier: Коэффициент для переработок (по умолчанию 1.5)
        tax_rate: Ставка налога (по умолчанию 13%)
    
    Returns:
        Словарь с расчётами:
        - base_salary: Базовая ставка
        - hours_worked: Отработанные часы
        - gross: Оклад до коэффициентов
        - district_coefficient: Районный коэффициент
        - gross_with_coefficient: Оклад с районным коэффициентом
        - northern_allowance: Северная надбавка
        - overtime_hours: Переработанные часы
        - overtime_pay: Оплата за переработки
        - bonus: Бонус
        - total: Итого до налогов
        - tax: Налог
        - net: К выплате
    
    Raises:
        SalaryCalculationError: При невалидных входных данных
    """
    # Валидация входных данных
    validate_salary_inputs(
        base_salary=base_salary,
        hours_worked=hours_worked,
        northern_allowance_rate=northern_allowance_rate,
        district_coefficient=district_coefficient,
        overtime_hours=overtime_hours,
        bonus=bonus
    )
    
    # Базовый оклад (ставка * отработанные часы)
    gross = base_salary * hours_worked
    
    # Районный коэффициент (по умолчанию 1.0)
    if district_coefficient is None:
        district_coefficient = Decimal("1.0")
    
    gross_with_coefficient = gross * district_coefficient
    
    # Северная надбавка (процент от оклада с коэффициентом)
    northern_allowance = Decimal("0")
    if northern_allowance_rate is not None and northern_allowance_rate > 0:
        northern_allowance = gross_with_coefficient * (northern_allowance_rate / Decimal("100"))
    
    # Переработки (сверхурочные часы с повышенной ставкой)
    overtime_pay = Decimal("0")
    if overtime_hours is not None and overtime_hours > 0:
        # Ставка за переработку = базовая ставка * коэффициент переработки
        overtime_rate = base_salary * overtime_multiplier
        overtime_pay = overtime_rate * overtime_hours
    
    # Бонус
    bonus_amount = bonus or Decimal("0")
    
    # Итого до налогов
    total = gross_with_coefficient + northern_allowance + overtime_pay + bonus_amount
    
    # Налог
    tax = total * tax_rate
    
    # К выплате
    net = total - tax
    
    return {
        "base_salary": base_salary,
        "hours_worked": hours_worked,
        "gross": gross,
        "district_coefficient": district_coefficient,
        "gross_with_coefficient": gross_with_coefficient,
        "northern_allowance": northern_allowance,
        "overtime_hours": overtime_hours or Decimal("0"),
        "overtime_pay": overtime_pay,
        "bonus": bonus_amount,
        "total": total,
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
    report = "💰 Расчёт зарплаты:\n\n"
    
    # Базовая информация
    report += f"📊 Базовая ставка: {calculation['base_salary']:.2f} ₽/час\n"
    report += f"⏰ Отработано часов: {calculation['hours_worked']:.0f}\n"
    report += f"💵 Оклад: {calculation['gross']:.2f} ₽\n"
    
    # Районный коэффициент
    if calculation['district_coefficient'] != Decimal("1.0"):
        report += f"📍 Районный коэффициент ({calculation['district_coefficient']:.2f}): "
        report += f"{calculation['gross_with_coefficient']:.2f} ₽\n"
    
    # Северная надбавка
    if calculation['northern_allowance'] > 0:
        report += f"❄️ Северная надбавка: {calculation['northern_allowance']:.2f} ₽\n"
    
    # Переработки
    if calculation['overtime_hours'] > 0:
        report += f"⏱️ Переработки ({calculation['overtime_hours']:.0f} ч): "
        report += f"{calculation['overtime_pay']:.2f} ₽\n"
    
    # Бонус
    if calculation['bonus'] > 0:
        report += f"🎁 Бонус: {calculation['bonus']:.2f} ₽\n"
    
    report += "\n"
    report += f"📈 Итого до налогов: {calculation['total']:.2f} ₽\n"
    report += f"📉 Налог (13%): {calculation['tax']:.2f} ₽\n"
    report += f"✅ К выплате: {calculation['net']:.2f} ₽"
    
    return report

