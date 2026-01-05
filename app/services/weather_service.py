"""
Сервис для получения и форматирования данных о погоде.
"""

import logging
import os
import time
from typing import Optional
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import aiohttp

# Загружаем переменные окружения
load_dotenv()

logger = logging.getLogger(__name__)

# Координаты Ванкорского месторождения (читаются из .env)
VANKOR_LATITUDE = float(os.getenv("VANKOR_LATITUDE", "69.5"))
VANKOR_LONGITUDE = float(os.getenv("VANKOR_LONGITUDE", "88.0"))
VANKOR_NAME = os.getenv("VANKOR_NAME", "Ванкорское месторождение")

# Длительность кэша по умолчанию (30 минут в секундах)
DEFAULT_CACHE_DURATION = 1800


class WeatherCache:
    """
    Класс для кэширования данных о погоде.
    
    Потокобезопасный кэш с TTL (time-to-live).
    """
    
    def __init__(self, cache_duration: int = DEFAULT_CACHE_DURATION):
        """
        Инициализирует кэш погоды.
        
        Args:
            cache_duration: Длительность кэша в секундах (по умолчанию 1800 секунд = 30 минут)
        """
        self._cache: Optional[dict] = None
        self._cache_timestamp: float = 0
        self._cache_duration = cache_duration
    
    def get(self) -> Optional[dict]:
        """
        Получить данные из кэша, если они ещё актуальны.
        
        Returns:
            Данные о погоде или None, если кэш пуст или устарел
        """
        if self._cache is None:
            return None
        
        current_time = time.time()
        if (current_time - self._cache_timestamp) >= self._cache_duration:
            # Кэш устарел
            self._cache = None
            self._cache_timestamp = 0
            return None
        
        return self._cache
    
    def set(self, weather_data: dict) -> None:
        """
        Сохранить данные о погоде в кэш.
        
        Args:
            weather_data: Данные о погоде для кэширования
        """
        self._cache = weather_data
        self._cache_timestamp = time.time()
    
    def clear(self) -> None:
        """Очистить кэш."""
        self._cache = None
        self._cache_timestamp = 0
    
    def is_valid(self) -> bool:
        """
        Проверить, актуален ли кэш.
        
        Returns:
            True если кэш существует и не устарел, False в противном случае
        """
        if self._cache is None:
            return False
        
        current_time = time.time()
        return (current_time - self._cache_timestamp) < self._cache_duration


# Глобальный экземпляр кэша (создаётся один раз при импорте модуля)
_weather_cache = WeatherCache()


async def get_weather(api_key: Optional[str] = None, cache: Optional[WeatherCache] = None) -> Optional[dict]:
    """
    Получает данные о погоде для Ванкорского месторождения.
    
    Использует кэширование на 30 минут для уменьшения количества запросов к API.
    
    Args:
        api_key: API ключ для OpenWeatherMap (если не указан, берётся из переменных окружения)
        cache: Экземпляр WeatherCache для кэширования (если не указан, используется глобальный)
    
    Returns:
        Словарь с данными о погоде или None в случае ошибки
    """
    # Используем переданный кэш или глобальный
    weather_cache = cache if cache is not None else _weather_cache
    
    # Проверяем кэш
    cached_data = weather_cache.get()
    if cached_data is not None:
        logger.debug("Возвращаем данные из кэша")
        return cached_data
    
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
                    weather_cache.set(weather_data)
                    
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
    
    # Эмодзи для "ощущается как" (используем тот же, что и для температуры)
    feels_like_emoji = temp_emoji
    
    # Форматируем дату из timestamp
    date_str = ""
    timestamp = weather_data.get("timestamp")
    if timestamp:
        try:
            # Парсим ISO формат timestamp
            if timestamp.endswith('Z'):
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                dt = datetime.fromisoformat(timestamp)
            
            # Конвертируем в локальное время (UTC+7 для Красноярска/Ванкора)
            # Используем UTC+7 как приблизительное время для Ванкора
            local_dt = dt + timedelta(hours=7)
            
            # Форматируем дату на русском языке
            months = [
                "января", "февраля", "марта", "апреля", "мая", "июня",
                "июля", "августа", "сентября", "октября", "ноября", "декабря"
            ]
            date_str = f"{local_dt.day} {months[local_dt.month - 1]} {local_dt.year}, {local_dt.hour:02d}:{local_dt.minute:02d}"
        except Exception as e:
            # Если не удалось распарсить, используем текущее время
            logger.debug(f"Не удалось распарсить timestamp {timestamp}: {e}")
            try:
                dt = datetime.now(timezone.utc) + timedelta(hours=7)
                months = [
                    "января", "февраля", "марта", "апреля", "мая", "июня",
                    "июля", "августа", "сентября", "октября", "ноября", "декабря"
                ]
                date_str = f"{dt.day} {months[dt.month - 1]} {dt.year}, {dt.hour:02d}:{dt.minute:02d}"
            except Exception:
                date_str = ""
    
    report = f"🌍 {location}\n"
    if date_str:
        report += f"📅 {date_str}\n"
    report += "\n"
    report += f"{temp_emoji} Температура: {temp}°C\n"
    
    if feels_like != temp:
        report += f"{feels_like_emoji} Ощущается как: {feels_like}°C\n"
    
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

