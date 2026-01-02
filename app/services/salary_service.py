"""
Сервис для расчёта зарплаты.
"""

from typing import Optional
from decimal import Decimal


def calculate_salary(
    base_salary: Decimal,
    hours_worked: Decimal,
    bonus: Optional[Decimal] = None,
    tax_rate: Decimal = Decimal("0.13")
) -> dict[str, Decimal]:
    """
    Рассчитывает зарплату с учётом отработанных часов, бонусов и налогов.
    
    Args:
        base_salary: Базовая ставка за час
        hours_worked: Отработанные часы
        bonus: Бонус (опционально)
        tax_rate: Ставка налога (по умолчанию 13%)
    
    Returns:
        Словарь с расчётами: gross, bonus, total, tax, net
    """
    gross = base_salary * hours_worked
    bonus_amount = bonus or Decimal("0")
    total = gross + bonus_amount
    tax = total * tax_rate
    net = total - tax
    
    return {
        "gross": gross,
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
    return (
        f"💰 Расчёт зарплаты:\n\n"
        f"Оклад: {calculation['gross']:.2f} ₽\n"
        f"Бонус: {calculation['bonus']:.2f} ₽\n"
        f"Итого до налогов: {calculation['total']:.2f} ₽\n"
        f"Налог (13%): {calculation['tax']:.2f} ₽\n"
        f"К выплате: {calculation['net']:.2f} ₽"
    )

