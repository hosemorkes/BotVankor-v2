"""
Тесты для сервиса погоды.
"""

import pytest
import aiohttp
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.weather_service import (
    format_weather_report,
    get_weather,
    WeatherCache,
    VANKOR_LATITUDE,
    VANKOR_LONGITUDE,
    VANKOR_NAME
)


def test_format_weather_report():
    """Тест форматирования отчёта о погоде."""
    weather_data = {
        "location": "Ванкорское месторождение",
        "temperature": -15,
        "feels_like": -20,
        "description": "ясно",
        "humidity": 65,
        "pressure": 1013,
        "wind_speed": 5.2,
        "wind_direction": "С",
        "visibility": 10.0
    }
    
    report = format_weather_report(weather_data)
    assert isinstance(report, str)
    assert "Ванкорское месторождение" in report
    assert "-15" in report
    assert "ясно" in report
    assert "65" in report  # влажность
    assert "1013" in report  # давление


def test_format_weather_report_empty():
    """Тест форматирования при отсутствии данных."""
    report = format_weather_report(None)
    assert isinstance(report, str)
    assert "Не удалось получить" in report


def test_format_weather_report_minimal():
    """Тест форматирования с минимальными данными."""
    weather_data = {
        "location": "Ванкор",
        "temperature": 0,
        "description": "облачно"
    }
    
    report = format_weather_report(weather_data)
    assert isinstance(report, str)
    assert "Ванкор" in report
    assert "0" in report


def test_wind_direction():
    """Тест определения направления ветра."""
    from app.services.weather_service import _get_wind_direction
    
    assert _get_wind_direction(0) == "С"
    assert _get_wind_direction(90) == "В"
    assert _get_wind_direction(180) == "Ю"
    assert _get_wind_direction(270) == "З"
    assert _get_wind_direction(None) == "неизвестно"


@pytest.mark.asyncio
async def test_get_weather_success():
    """Тест успешного получения погоды."""
    # Создаём новый экземпляр кэша для теста
    test_cache = WeatherCache(cache_duration=0)  # Кэш сразу устаревает
    
    mock_response = {
        "main": {
            "temp": -20,
            "feels_like": -25,
            "humidity": 70,
            "pressure": 1015
        },
        "weather": [{
            "description": "ясно"
        }],
        "wind": {
            "speed": 3.5,
            "deg": 90
        },
        "visibility": 10000
    }
    
    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_response_obj = AsyncMock()
        mock_response_obj.status = 200
        mock_response_obj.json = AsyncMock(return_value=mock_response)
        mock_get.return_value.__aenter__.return_value = mock_response_obj
        
        with patch.dict('os.environ', {'WEATHER_API_KEY': 'test_key'}):
            result = await get_weather(cache=test_cache)
            
            assert result is not None
            assert result["location"] == VANKOR_NAME
            assert result["temperature"] == -20
            assert result["feels_like"] == -25
            assert result["description"] == "Ясно"


@pytest.mark.asyncio
async def test_get_weather_no_api_key():
    """Тест получения погоды без API ключа."""
    # Создаём новый экземпляр кэша для теста
    test_cache = WeatherCache(cache_duration=0)  # Кэш сразу устаревает
    
    with patch.dict('os.environ', {}, clear=True):
        result = await get_weather(cache=test_cache)
        assert result is None


@pytest.mark.asyncio
async def test_get_weather_api_error():
    """Тест обработки ошибки API."""
    # Создаём новый экземпляр кэша для теста
    test_cache = WeatherCache(cache_duration=0)  # Кэш сразу устаревает
    
    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_response_obj = AsyncMock()
        mock_response_obj.status = 401
        mock_response_obj.text = AsyncMock(return_value="Unauthorized")
        mock_get.return_value.__aenter__.return_value = mock_response_obj
        
        with patch.dict('os.environ', {'WEATHER_API_KEY': 'test_key'}):
            result = await get_weather(cache=test_cache)
            assert result is None


@pytest.mark.asyncio
async def test_get_weather_network_error():
    """Тест обработки сетевой ошибки."""
    # Создаём новый экземпляр кэша для теста
    test_cache = WeatherCache(cache_duration=0)  # Кэш сразу устаревает
    
    with patch('aiohttp.ClientSession.get', side_effect=aiohttp.ClientError("Network error")):
        with patch.dict('os.environ', {'WEATHER_API_KEY': 'test_key'}):
            result = await get_weather(cache=test_cache)
            assert result is None


def test_vankor_coordinates():
    """Тест координат Ванкорского месторождения."""
    assert VANKOR_LATITUDE == 69.5
    assert VANKOR_LONGITUDE == 88.0
    assert VANKOR_NAME == "Ванкорское месторождение"


def test_weather_cache():
    """Тест класса WeatherCache."""
    cache = WeatherCache(cache_duration=60)  # 60 секунд
    
    # Кэш пуст
    assert cache.get() is None
    assert cache.is_valid() is False
    
    # Сохраняем данные
    test_data = {"temperature": 20, "description": "ясно"}
    cache.set(test_data)
    
    # Проверяем, что данные есть
    assert cache.get() == test_data
    assert cache.is_valid() is True
    
    # Очищаем кэш
    cache.clear()
    assert cache.get() is None
    assert cache.is_valid() is False


def test_weather_cache_expiration():
    """Тест истечения срока действия кэша."""
    cache = WeatherCache(cache_duration=0)  # Кэш сразу устаревает
    
    test_data = {"temperature": 20}
    cache.set(test_data)
    
    # Кэш должен быть пустым, так как duration=0
    assert cache.get() is None
    assert cache.is_valid() is False

