"""
Тесты для сервиса расчёта зарплаты.
"""

import pytest
from decimal import Decimal

from app.services.salary_service import calculate_salary, format_salary_report


def test_calculate_salary_basic():
    """Тест базового расчёта зарплаты."""
    result = calculate_salary(
        base_salary=Decimal("1000"),
        hours_worked=Decimal("160"),
        tax_rate=Decimal("0.13")
    )
    
    assert result["gross"] == Decimal("160000")
    assert result["bonus"] == Decimal("0")
    assert result["total"] == Decimal("160000")
    assert result["tax"] == Decimal("20800")
    assert result["net"] == Decimal("139200")


def test_calculate_salary_with_bonus():
    """Тест расчёта зарплаты с бонусом."""
    result = calculate_salary(
        base_salary=Decimal("1000"),
        hours_worked=Decimal("160"),
        bonus=Decimal("20000"),
        tax_rate=Decimal("0.13")
    )
    
    assert result["gross"] == Decimal("160000")
    assert result["bonus"] == Decimal("20000")
    assert result["total"] == Decimal("180000")
    assert result["tax"] == Decimal("23400")
    assert result["net"] == Decimal("156600")


def test_format_salary_report():
    """Тест форматирования отчёта о зарплате."""
    calculation = {
        "gross": Decimal("160000"),
        "bonus": Decimal("20000"),
        "total": Decimal("180000"),
        "tax": Decimal("23400"),
        "net": Decimal("156600"),
    }
    
    report = format_salary_report(calculation)
    assert "💰 Расчёт зарплаты" in report
    assert "160000.00" in report
    assert "156600.00" in report

