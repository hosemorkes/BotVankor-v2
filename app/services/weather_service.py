"""
Сервис для получения и форматирования данных о погоде.
"""

import logging
import os
import time
from typing import Optional
from datetime import datetime, timezone
from dotenv import load_dotenv
import aiohttp

# Загружаем переменные окружения
load_dotenv()

logger = logging.getLogger(__name__)

# Координаты Ванкорского месторождения (читаются из .env)
VANKOR_LATITUDE = float(os.getenv("VANKOR_LATITUDE", "69.5"))
VANKOR_LONGITUDE = float(os.getenv("VANKOR_LONGITUDE", "88.0"))
VANKOR_NAME = os.getenv("VANKOR_NAME", "Ванкорское месторождение")

# Кэш для хранения данных о погоде
_weather_cache: Optional[dict] = None
_cache_timestamp: float = 0
CACHE_DURATION = 600  # 10 минут в секундах


async def get_weather(api_key: Optional[str] = None) -> Optional[dict]:
    """
    Получает данные о погоде для Ванкорского месторождения.
    
    Использует кэширование на 10 минут для уменьшения количества запросов к API.
    
    Args:
        api_key: API ключ для OpenWeatherMap (если не указан, берётся из переменных окружения)
    
    Returns:
        Словарь с данными о погоде или None в случае ошибки
    """
    global _weather_cache, _cache_timestamp
    
    # Проверяем кэш
    current_time = time.time()
    if _weather_cache and (current_time - _cache_timestamp) < CACHE_DURATION:
        logger.debug("Возвращаем данные из кэша")
        return _weather_cache
    
    # Получаем API ключ
    if not api_key:
        api_key = os.getenv("WEATHER_API_KEY")
    
    if not api_key:
        logger.error("WEATHER_API_KEY не установлен в переменных окружения")
        return None
    
    # Формируем URL для запроса
    url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?lat={VANKOR_LATITUDE}&lon={VANKOR_LONGITUDE}"
        f"&appid={api_key}&units=metric&lang=ru"
    )
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Формируем структурированные данные
                    weather_data = {
                        "location": VANKOR_NAME,
                        "temperature": round(data["main"]["temp"]),
                        "feels_like": round(data["main"]["feels_like"]),
                        "description": data["weather"][0]["description"].capitalize(),
                        "humidity": data["main"]["humidity"],
                        "pressure": data["main"]["pressure"],
                        "wind_speed": data.get("wind", {}).get("speed", 0),
                        "wind_direction": _get_wind_direction(data.get("wind", {}).get("deg")),
                        "visibility": data.get("visibility", 0) / 1000 if data.get("visibility") else None,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    
                    # Сохраняем в кэш
                    _weather_cache = weather_data
                    _cache_timestamp = current_time
                    
                    logger.info(f"Получены данные о погоде для {VANKOR_NAME}")
                    return weather_data
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка API погоды: статус {response.status}, ответ: {error_text}")
                    return None
                    
    except aiohttp.ClientError as e:
        logger.error(f"Ошибка сети при запросе погоды: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении погоды: {e}")
        return None


def _get_wind_direction(degrees: Optional[float]) -> str:
    """
    Преобразует направление ветра из градусов в текстовое описание.
    
    Args:
        degrees: Направление в градусах (0-360)
    
    Returns:
        Строка с направлением ветра
    """
    if degrees is None:
        return "неизвестно"
    
    directions = [
        "С", "ССВ", "СВ", "ВСВ", "В", "ВЮВ", "ЮВ", "ЮЮВ",
        "Ю", "ЮЮЗ", "ЮЗ", "ЗЮЗ", "З", "ЗСЗ", "СЗ", "ССЗ"
    ]
    index = int((degrees + 11.25) / 22.5) % 16
    return directions[index]


def format_weather_report(weather_data: dict) -> str:
    """
    Форматирует данные о погоде для вывода пользователю.
    
    Args:
        weather_data: Данные о погоде из get_weather
    
    Returns:
        Отформатированная строка с информацией о погоде
    """
    if not weather_data:
        return "❌ Не удалось получить данные о погоде. Попробуйте позже."
    
    location = weather_data.get("location", "Ванкор")
    temp = weather_data.get("temperature", "N/A")
    feels_like = weather_data.get("feels_like", "N/A")
    description = weather_data.get("description", "нет данных")
    humidity = weather_data.get("humidity", "N/A")
    pressure = weather_data.get("pressure", "N/A")
    wind_speed = weather_data.get("wind_speed", 0)
    wind_dir = weather_data.get("wind_direction", "неизвестно")
    visibility = weather_data.get("visibility")
    
    # Эмодзи для температуры
    if isinstance(temp, (int, float)):
        if temp < -20:
            temp_emoji = "🥶"
        elif temp < 0:
            temp_emoji = "❄️"
        elif temp < 10:
            temp_emoji = "🧊"
        elif temp < 20:
            temp_emoji = "🌤️"
        else:
            temp_emoji = "☀️"
    else:
        temp_emoji = "🌡️"
    
    report = f"🌍 {location}\n\n"
    report += f"{temp_emoji} Температура: {temp}°C\n"
    
    if feels_like != temp:
        report += f"   Ощущается как: {feels_like}°C\n"
    
    report += f"☁️ {description}\n\n"
    report += f"💧 Влажность: {humidity}%\n"
    report += f"📊 Давление: {pressure} мм рт.ст.\n"
    
    if wind_speed > 0:
        report += f"💨 Ветер: {wind_speed} м/с, {wind_dir}\n"
    else:
        report += f"💨 Ветер: штиль\n"
    
    if visibility:
        report += f"👁️ Видимость: {visibility:.1f} км\n"
    
    return report

