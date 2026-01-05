"""
Тесты для сервиса расчёта зарплаты (вахтовый метод).
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
        hourly_rate=Decimal("1000"),
        days_worked=Decimal("15")
    )
    
    # Часы по табелю = 15 * 11 = 165
    assert result["hours_by_timesheet"] == Decimal("165")
    # Оплата по окладу = 165 * 1000 = 165000
    assert result["salary_by_position"] == Decimal("165000")
    # Премия месячная = 165000 * 0.33 = 54450
    assert result["monthly_bonus"] == Decimal("54450")
    # Доплата за вахтовый метод = 15 * 740 = 11100
    assert result["shift_method_payment"] == Decimal("11100")
    # Всего начислено = 165000 + 54450 + 11100 = 230550
    assert result["total_accrued"] == Decimal("230550")
    # Налог = (230550 - 11100) * 0.13 = 219450 * 0.13 = 28528.5
    assert result["tax"] == Decimal("28528.50")
    # К выплате = 230550 - 28528.5 = 202021.5
    assert result["net"] == Decimal("202021.50")


def test_calculate_salary_with_night_hours():
    """Тест расчёта зарплаты с ночными часами."""
    result = calculate_salary(
        hourly_rate=Decimal("1000"),
        days_worked=Decimal("15"),
        night_hours=Decimal("20")
    )
    
    # Ночные = 20 * 1000 * 0.4 = 8000
    assert result["night_shift_payment"] == Decimal("8000")
    # Премия = (165000 + 8000) * 0.33 = 173000 * 0.33 = 57090
    assert result["monthly_bonus"] == Decimal("57090")


def test_calculate_salary_with_idle_days():
    """Тест расчёта зарплаты с днями простоя."""
    result = calculate_salary(
        hourly_rate=Decimal("1000"),
        days_worked=Decimal("15"),
        idle_days=Decimal("2")
    )
    
    # Простой = 2 * 11 * 1000 * (2/3) = 14666.67
    assert result["idle_payment"] == Decimal("14666.67")


def test_calculate_salary_with_travel_days():
    """Тест расчёта зарплаты с днями в пути."""
    result = calculate_salary(
        hourly_rate=Decimal("1000"),
        days_worked=Decimal("15"),
        travel_days=Decimal("2")
    )
    
    # Дни в пути = 2 * 1000 * 8 = 16000
    assert result["travel_payment"] == Decimal("16000")
    # Вахтовый метод = (15 + 2) * 740 = 12580
    assert result["shift_method_payment"] == Decimal("12580")


def test_calculate_salary_with_holiday_days():
    """Тест расчёта зарплаты с праздничными днями."""
    result = calculate_salary(
        hourly_rate=Decimal("1000"),
        days_worked=Decimal("15"),
        holiday_days=Decimal("1")
    )
    
    # Праздники = 1 * 1000 * 11 = 11000
    assert result["holiday_payment"] == Decimal("11000")


def test_calculate_salary_with_allowances():
    """Тест расчёта зарплаты с надбавками."""
    result = calculate_salary(
        hourly_rate=Decimal("1000"),
        days_worked=Decimal("15"),
        regional_allowance_rate=Decimal("20"),
        northern_allowance_rate=Decimal("50")
    )
    
    # Оклад = 165000
    # Премия = 165000 * 0.33 = 54450
    # Региональная = (165000 + 54450) * 0.2 = 43890
    assert result["regional_allowance"] == Decimal("43890")
    # Северная = (165000 + 54450) * 0.5 = 109725
    assert result["northern_allowance"] == Decimal("109725")


def test_calculate_salary_full():
    """Тест полного расчёта зарплаты со всеми параметрами."""
    result = calculate_salary(
        hourly_rate=Decimal("1000"),
        days_worked=Decimal("15"),
        night_hours=Decimal("20"),
        idle_days=Decimal("2"),
        travel_days=Decimal("2"),
        holiday_days=Decimal("1"),
        additional_payments=Decimal("5000"),
        regional_allowance_rate=Decimal("20"),
        northern_allowance_rate=Decimal("50")
    )
    
    # Проверяем основные компоненты
    assert result["hours_by_timesheet"] == Decimal("165")
    assert result["salary_by_position"] == Decimal("165000")
    assert result["holiday_payment"] == Decimal("11000")
    assert result["idle_payment"] == Decimal("14666.67")
    assert result["travel_payment"] == Decimal("16000")
    assert result["shift_method_payment"] == Decimal("12580")
    assert result["night_shift_payment"] == Decimal("8000")
    assert result["monthly_bonus"] == Decimal("57090")
    assert result["additional_payments"] == Decimal("5000")
    
    # Проверяем, что итоговая сумма положительная
    assert result["total_accrued"] > 0
    assert result["tax"] > 0
    assert result["net"] > 0


def test_validate_salary_inputs_valid():
    """Тест валидации валидных данных."""
    # Не должно вызывать исключений
    validate_salary_inputs(
        hourly_rate=Decimal("1000"),
        days_worked=Decimal("15"),
        night_hours=Decimal("20"),
        idle_days=Decimal("2"),
        travel_days=Decimal("2"),
        holiday_days=Decimal("1"),
        additional_payments=Decimal("5000"),
        regional_allowance_rate=Decimal("20"),
        northern_allowance_rate=Decimal("50")
    )


def test_validate_salary_inputs_invalid_hourly_rate():
    """Тест валидации невалидной часовой ставки."""
    with pytest.raises(SalaryCalculationError, match="Часовая ставка должна быть больше нуля"):
        validate_salary_inputs(
            hourly_rate=Decimal("0"),
            days_worked=Decimal("15")
        )


def test_validate_salary_inputs_invalid_days():
    """Тест валидации невалидных дней."""
    with pytest.raises(SalaryCalculationError, match="Количество отработанных дней не может быть отрицательным"):
        validate_salary_inputs(
            hourly_rate=Decimal("1000"),
            days_worked=Decimal("-5")
        )


def test_validate_salary_inputs_invalid_regional_allowance():
    """Тест валидации невалидной региональной надбавки."""
    with pytest.raises(SalaryCalculationError, match="Региональная надбавка должна быть от 0 до 100%"):
        validate_salary_inputs(
            hourly_rate=Decimal("1000"),
            days_worked=Decimal("15"),
            regional_allowance_rate=Decimal("150")
        )


def test_validate_salary_inputs_invalid_northern_allowance():
    """Тест валидации невалидной северной надбавки."""
    with pytest.raises(SalaryCalculationError, match="Северная надбавка должна быть от 0 до 100%"):
        validate_salary_inputs(
            hourly_rate=Decimal("1000"),
            days_worked=Decimal("15"),
            northern_allowance_rate=Decimal("-10")
        )


def test_format_salary_report():
    """Тест форматирования отчёта о зарплате."""
    calculation = {
        "hourly_rate": Decimal("1000"),
        "days_worked": Decimal("15"),
        "night_hours": Decimal("20"),
        "idle_days": Decimal("2"),
        "travel_days": Decimal("2"),
        "holiday_days": Decimal("1"),
        "hours_by_timesheet": Decimal("165"),
        "salary_by_position": Decimal("165000"),
        "holiday_payment": Decimal("11000"),
        "idle_payment": Decimal("14666.67"),
        "travel_payment": Decimal("16000"),
        "shift_method_payment": Decimal("12580"),
        "night_shift_payment": Decimal("8000"),
        "monthly_bonus": Decimal("57090"),
        "regional_allowance_rate": Decimal("20"),
        "regional_allowance": Decimal("43890"),
        "northern_allowance_rate": Decimal("50"),
        "northern_allowance": Decimal("109725"),
        "additional_payments": Decimal("5000"),
        "total_accrued": Decimal("500000"),
        "tax": Decimal("65000"),
        "net": Decimal("435000"),
    }
    
    report = format_salary_report(calculation)
    assert "💰 Расчёт зарплаты" in report
    assert "1000.00" in report
    assert "15" in report
    assert "165" in report
    assert "165000.00" in report
    assert "435000.00" in report


def test_format_salary_report_minimal():
    """Тест форматирования минимального отчёта (без дополнительных параметров)."""
    calculation = {
        "hourly_rate": Decimal("1000"),
        "days_worked": Decimal("15"),
        "night_hours": Decimal("0"),
        "idle_days": Decimal("0"),
        "travel_days": Decimal("0"),
        "holiday_days": Decimal("0"),
        "hours_by_timesheet": Decimal("165"),
        "salary_by_position": Decimal("165000"),
        "holiday_payment": Decimal("0"),
        "idle_payment": Decimal("0"),
        "travel_payment": Decimal("0"),
        "shift_method_payment": Decimal("11100"),
        "night_shift_payment": Decimal("0"),
        "monthly_bonus": Decimal("54450"),
        "regional_allowance_rate": Decimal("0"),
        "regional_allowance": Decimal("0"),
        "northern_allowance_rate": Decimal("0"),
        "northern_allowance": Decimal("0"),
        "additional_payments": Decimal("0"),
        "total_accrued": Decimal("230550"),
        "tax": Decimal("28528.50"),
        "net": Decimal("202021.50"),
    }
    
    report = format_salary_report(calculation)
    assert "💰 Расчёт зарплаты" in report
    assert "1000.00" in report
    assert "15" in report
    assert "202021.50" in report
