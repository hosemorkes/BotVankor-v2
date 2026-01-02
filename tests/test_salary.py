"""
Тесты для сервиса расчёта зарплаты.
"""

import pytest
from decimal import Decimal

from app.services.salary_service import (
    calculate_salary,
    format_salary_report,
    validate_salary_inputs,
    SalaryCalculationError
)


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
    assert result["district_coefficient"] == Decimal("1.0")
    assert result["northern_allowance"] == Decimal("0")
    assert result["overtime_hours"] == Decimal("0")
    assert result["overtime_pay"] == Decimal("0")


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


def test_calculate_salary_with_district_coefficient():
    """Тест расчёта зарплаты с районным коэффициентом."""
    result = calculate_salary(
        base_salary=Decimal("1000"),
        hours_worked=Decimal("160"),
        district_coefficient=Decimal("1.5"),
        tax_rate=Decimal("0.13")
    )
    
    assert result["gross"] == Decimal("160000")
    assert result["district_coefficient"] == Decimal("1.5")
    assert result["gross_with_coefficient"] == Decimal("240000")
    assert result["total"] == Decimal("240000")
    assert result["tax"] == Decimal("31200")
    assert result["net"] == Decimal("208800")


def test_calculate_salary_with_northern_allowance():
    """Тест расчёта зарплаты с северной надбавкой."""
    result = calculate_salary(
        base_salary=Decimal("1000"),
        hours_worked=Decimal("160"),
        northern_allowance_rate=Decimal("50"),
        tax_rate=Decimal("0.13")
    )
    
    assert result["gross"] == Decimal("160000")
    assert result["gross_with_coefficient"] == Decimal("160000")
    assert result["northern_allowance"] == Decimal("80000")  # 50% от 160000
    assert result["total"] == Decimal("240000")
    assert result["tax"] == Decimal("31200")
    assert result["net"] == Decimal("208800")


def test_calculate_salary_with_overtime():
    """Тест расчёта зарплаты с переработками."""
    result = calculate_salary(
        base_salary=Decimal("1000"),
        hours_worked=Decimal("160"),
        overtime_hours=Decimal("20"),
        overtime_multiplier=Decimal("1.5"),
        tax_rate=Decimal("0.13")
    )
    
    assert result["gross"] == Decimal("160000")
    assert result["overtime_hours"] == Decimal("20")
    assert result["overtime_pay"] == Decimal("30000")  # 1000 * 1.5 * 20
    assert result["total"] == Decimal("190000")
    assert result["tax"] == Decimal("24700")
    assert result["net"] == Decimal("165300")


def test_calculate_salary_full():
    """Тест полного расчёта зарплаты со всеми параметрами."""
    result = calculate_salary(
        base_salary=Decimal("1000"),
        hours_worked=Decimal("160"),
        district_coefficient=Decimal("1.5"),
        northern_allowance_rate=Decimal("50"),
        overtime_hours=Decimal("20"),
        bonus=Decimal("20000"),
        overtime_multiplier=Decimal("1.5"),
        tax_rate=Decimal("0.13")
    )
    
    # Базовый оклад
    assert result["gross"] == Decimal("160000")
    
    # С районным коэффициентом
    assert result["gross_with_coefficient"] == Decimal("240000")
    
    # Северная надбавка (50% от оклада с коэффициентом)
    assert result["northern_allowance"] == Decimal("120000")
    
    # Переработки
    assert result["overtime_pay"] == Decimal("30000")
    
    # Бонус
    assert result["bonus"] == Decimal("20000")
    
    # Итого до налогов: 240000 + 120000 + 30000 + 20000 = 410000
    assert result["total"] == Decimal("410000")
    
    # Налог 13%
    assert result["tax"] == Decimal("53300")
    
    # К выплате
    assert result["net"] == Decimal("356700")


def test_validate_salary_inputs_valid():
    """Тест валидации валидных данных."""
    # Не должно вызывать исключений
    validate_salary_inputs(
        base_salary=Decimal("1000"),
        hours_worked=Decimal("160"),
        northern_allowance_rate=Decimal("50"),
        district_coefficient=Decimal("1.5"),
        overtime_hours=Decimal("20"),
        bonus=Decimal("10000")
    )


def test_validate_salary_inputs_invalid_base_salary():
    """Тест валидации невалидной базовой ставки."""
    with pytest.raises(SalaryCalculationError, match="Базовая ставка должна быть больше нуля"):
        validate_salary_inputs(
            base_salary=Decimal("0"),
            hours_worked=Decimal("160")
        )


def test_validate_salary_inputs_invalid_hours():
    """Тест валидации невалидных часов."""
    with pytest.raises(SalaryCalculationError, match="Отработанные часы не могут быть отрицательными"):
        validate_salary_inputs(
            base_salary=Decimal("1000"),
            hours_worked=Decimal("-10")
        )


def test_validate_salary_inputs_invalid_northern_allowance():
    """Тест валидации невалидной северной надбавки."""
    with pytest.raises(SalaryCalculationError, match="Северная надбавка должна быть от 0 до 100%"):
        validate_salary_inputs(
            base_salary=Decimal("1000"),
            hours_worked=Decimal("160"),
            northern_allowance_rate=Decimal("150")
        )


def test_validate_salary_inputs_invalid_district_coefficient():
    """Тест валидации невалидного районного коэффициента."""
    with pytest.raises(SalaryCalculationError, match="Районный коэффициент должен быть от 1.0 до 3.0"):
        validate_salary_inputs(
            base_salary=Decimal("1000"),
            hours_worked=Decimal("160"),
            district_coefficient=Decimal("5.0")
        )


def test_validate_salary_inputs_invalid_overtime():
    """Тест валидации невалидных переработок."""
    with pytest.raises(SalaryCalculationError, match="Переработанные часы не могут превышать отработанные"):
        validate_salary_inputs(
            base_salary=Decimal("1000"),
            hours_worked=Decimal("160"),
            overtime_hours=Decimal("200")
        )


def test_format_salary_report():
    """Тест форматирования отчёта о зарплате."""
    calculation = {
        "base_salary": Decimal("1000"),
        "hours_worked": Decimal("160"),
        "gross": Decimal("160000"),
        "district_coefficient": Decimal("1.5"),
        "gross_with_coefficient": Decimal("240000"),
        "northern_allowance": Decimal("120000"),
        "overtime_hours": Decimal("20"),
        "overtime_pay": Decimal("30000"),
        "bonus": Decimal("20000"),
        "total": Decimal("410000"),
        "tax": Decimal("53300"),
        "net": Decimal("356700"),
    }
    
    report = format_salary_report(calculation)
    assert "💰 Расчёт зарплаты" in report
    assert "1000.00" in report
    assert "160" in report
    assert "1.50" in report
    assert "120000.00" in report
    assert "20" in report
    assert "30000.00" in report
    assert "20000.00" in report
    assert "410000.00" in report
    assert "53300.00" in report
    assert "356700.00" in report


def test_format_salary_report_minimal():
    """Тест форматирования минимального отчёта (без дополнительных параметров)."""
    calculation = {
        "base_salary": Decimal("1000"),
        "hours_worked": Decimal("160"),
        "gross": Decimal("160000"),
        "district_coefficient": Decimal("1.0"),
        "gross_with_coefficient": Decimal("160000"),
        "northern_allowance": Decimal("0"),
        "overtime_hours": Decimal("0"),
        "overtime_pay": Decimal("0"),
        "bonus": Decimal("0"),
        "total": Decimal("160000"),
        "tax": Decimal("20800"),
        "net": Decimal("139200"),
    }
    
    report = format_salary_report(calculation)
    assert "💰 Расчёт зарплаты" in report
    assert "1000.00" in report
    assert "160" in report
    assert "160000.00" in report
    assert "139200.00" in report

