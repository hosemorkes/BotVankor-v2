"""
Тесты для сервиса погоды.
"""

import pytest

from app.services.weather_service import format_weather_report


def test_format_weather_report():
    """Тест форматирования отчёта о погоде."""
    weather_data = {
        "city": "Москва",
        "temperature": 20,
        "description": "ясно"
    }
    
    report = format_weather_report(weather_data)
    assert isinstance(report, str)

