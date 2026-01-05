"""
Сервис для получения и форматирования прогноза погоды на 7 дней.
"""

import logging
import os
import time
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from dotenv import load_dotenv
import aiohttp

# Загружаем переменные окружения
load_dotenv()

logger = logging.getLogger(__name__)

# Координаты Ванкорского месторождения (читаются из .env)
VANKOR_LATITUDE = float(os.getenv("VANKOR_LATITUDE", "69.5"))
VANKOR_LONGITUDE = float(os.getenv("VANKOR_LONGITUDE", "88.0"))
VANKOR_NAME = os.getenv("VANKOR_NAME", "Ванкорское месторождение")

# Длительность кэша по умолчанию (60 минут в секундах)
DEFAULT_CACHE_DURATION = 3600


class ForecastCache:
    """
    Класс для кэширования данных прогноза погоды.
    
    Потокобезопасный кэш с TTL (time-to-live).
    """
    
    def __init__(self, cache_duration: int = DEFAULT_CACHE_DURATION):
        """
        Инициализирует кэш прогноза погоды.
        
        Args:
            cache_duration: Длительность кэша в секундах (по умолчанию 3600 секунд = 60 минут)
        """
        self._cache: Optional[dict] = None
        self._cache_timestamp: float = 0
        self._cache_duration = cache_duration
    
    def get(self) -> Optional[dict]:
        """
        Получить данные из кэша, если они ещё актуальны.
        
        Returns:
            Данные прогноза или None, если кэш пуст или устарел
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
    
    def set(self, forecast_data: dict) -> None:
        """
        Сохранить данные прогноза в кэш.
        
        Args:
            forecast_data: Данные прогноза для кэширования
        """
        self._cache = forecast_data
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
_forecast_cache = ForecastCache()


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


def _get_temp_emoji(temp: float) -> str:
    """
    Возвращает эмодзи для температуры.
    
    Args:
        temp: Температура в градусах Цельсия
    
    Returns:
        Эмодзи для температуры
    """
    if temp < -20:
        return "🥶"
    elif temp < 0:
        return "❄️"
    elif temp < 10:
        return "🧊"
    elif temp < 20:
        return "🌤️"
    else:
        return "☀️"


async def get_7_day_forecast(
    api_key: Optional[str] = None,
    cache: Optional[ForecastCache] = None
) -> Optional[dict]:
    """
    Получает прогноз погоды на 7 дней для Ванкорского месторождения.
    
    Использует OpenWeatherMap API /forecast endpoint (прогноз на 5 дней с интервалом 3 часа).
    Данные группируются по дням для отображения прогноза на неделю.
    
    Args:
        api_key: API ключ для OpenWeatherMap (если не указан, берётся из переменных окружения)
        cache: Экземпляр ForecastCache для кэширования (если не указан, используется глобальный)
    
    Returns:
        Словарь с данными прогноза или None в случае ошибки
    """
    # Используем переданный кэш или глобальный
    forecast_cache = cache if cache is not None else _forecast_cache
    
    # Проверяем кэш
    cached_data = forecast_cache.get()
    if cached_data is not None:
        logger.debug("Возвращаем данные прогноза из кэша")
        return cached_data
    
    # Получаем API ключ
    if not api_key:
        api_key = os.getenv("WEATHER_API_KEY")
    
    if not api_key:
        logger.error("WEATHER_API_KEY не установлен в переменных окружения")
        return None
    
    # Формируем URL для запроса прогноза (5 дней с интервалом 3 часа)
    url = (
        f"https://api.openweathermap.org/data/2.5/forecast"
        f"?lat={VANKOR_LATITUDE}&lon={VANKOR_LONGITUDE}"
        f"&appid={api_key}&units=metric&lang=ru&cnt=40"
    )
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Группируем прогнозы по дням
                    daily_forecasts = _group_forecasts_by_day(data.get("list", []))
                    
                    # Формируем структурированные данные
                    forecast_data = {
                        "location": VANKOR_NAME,
                        "daily_forecasts": daily_forecasts,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    
                    # Сохраняем в кэш
                    forecast_cache.set(forecast_data)
                    
                    logger.info(f"Получен прогноз погоды на {len(daily_forecasts)} дней для {VANKOR_NAME}")
                    return forecast_data
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка API прогноза погоды: статус {response.status}, ответ: {error_text}")
                    return None
                    
    except aiohttp.ClientError as e:
        logger.error(f"Ошибка сети при запросе прогноза погоды: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении прогноза погоды: {e}")
        return None


def _group_forecasts_by_day(forecast_list: List[dict]) -> List[dict]:
    """
    Группирует прогнозы по дням и вычисляет средние/минимальные/максимальные значения.
    
    Args:
        forecast_list: Список прогнозов из API (каждые 3 часа)
    
    Returns:
        Список словарей с прогнозами по дням
    """
    # Группируем по дням
    daily_data = defaultdict(lambda: {
        "temps": [],
        "feels_like": [],
        "descriptions": [],
        "humidity": [],
        "pressure": [],
        "wind_speeds": [],
        "wind_directions": [],
        "timestamps": []
    })
    
    # Конвертируем UTC в локальное время (UTC+7)
    timezone_offset = timedelta(hours=7)
    
    for forecast in forecast_list:
        # Парсим timestamp
        dt_utc = datetime.fromtimestamp(forecast["dt"], tz=timezone.utc)
        dt_local = dt_utc + timezone_offset
        date_key = dt_local.date()
        
        # Собираем данные
        main = forecast.get("main", {})
        weather = forecast.get("weather", [{}])[0]
        wind = forecast.get("wind", {})
        
        daily_data[date_key]["temps"].append(main.get("temp", 0))
        daily_data[date_key]["feels_like"].append(main.get("feels_like", 0))
        daily_data[date_key]["descriptions"].append(weather.get("description", ""))
        daily_data[date_key]["humidity"].append(main.get("humidity", 0))
        daily_data[date_key]["pressure"].append(main.get("pressure", 0))
        daily_data[date_key]["wind_speeds"].append(wind.get("speed", 0))
        daily_data[date_key]["wind_directions"].append(wind.get("deg"))
        daily_data[date_key]["timestamps"].append(dt_local.isoformat())
    
    # Формируем итоговые данные по дням
    daily_forecasts = []
    for date_key in sorted(daily_data.keys())[:7]:  # Берем максимум 7 дней
        day_data = daily_data[date_key]
        
        # Вычисляем средние и экстремальные значения
        temps = day_data["temps"]
        feels_like_list = day_data["feels_like"]
        
        # Самое частое описание погоды
        descriptions = day_data["descriptions"]
        most_common_desc = max(set(descriptions), key=descriptions.count) if descriptions else "нет данных"
        
        daily_forecast = {
            "date": date_key,
            "date_str": _format_date(date_key),
            "temp_min": round(min(temps)) if temps else 0,
            "temp_max": round(max(temps)) if temps else 0,
            "temp_avg": round(sum(temps) / len(temps)) if temps else 0,
            "feels_like_min": round(min(feels_like_list)) if feels_like_list else 0,
            "feels_like_max": round(max(feels_like_list)) if feels_like_list else 0,
            "description": most_common_desc.capitalize(),
            "humidity_avg": round(sum(day_data["humidity"]) / len(day_data["humidity"])) if day_data["humidity"] else 0,
            "pressure_avg": round(sum(day_data["pressure"]) / len(day_data["pressure"])) if day_data["pressure"] else 0,
            "wind_speed_max": round(max(day_data["wind_speeds"]), 1) if day_data["wind_speeds"] else 0,
            "wind_direction": _get_wind_direction(
                sum([d for d in day_data["wind_directions"] if d is not None]) / 
                len([d for d in day_data["wind_directions"] if d is not None])
                if any(day_data["wind_directions"]) else None
            )
        }
        
        daily_forecasts.append(daily_forecast)
    
    return daily_forecasts


def _format_date(date_obj) -> str:
    """
    Форматирует дату на русском языке.
    
    Args:
        date_obj: Объект date
    
    Returns:
        Отформатированная строка с датой
    """
    months = [
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря"
    ]
    
    weekdays = [
        "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"
    ]
    
    weekday = weekdays[date_obj.weekday()]
    return f"{weekday}, {date_obj.day} {months[date_obj.month - 1]}"


def format_7_day_forecast_report(forecast_data: dict) -> str:
    """
    Форматирует прогноз погоды на 7 дней для вывода пользователю.
    
    Args:
        forecast_data: Данные прогноза из get_7_day_forecast
    
    Returns:
        Отформатированная строка с прогнозом погоды
    """
    if not forecast_data or not forecast_data.get("daily_forecasts"):
        return "❌ Не удалось получить прогноз погоды. Попробуйте позже."
    
    location = forecast_data.get("location", "Ванкор")
    daily_forecasts = forecast_data.get("daily_forecasts", [])
    
    # Форматируем дату получения прогноза
    timestamp = forecast_data.get("timestamp")
    date_str = ""
    if timestamp:
        try:
            if timestamp.endswith('Z'):
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                dt = datetime.fromisoformat(timestamp)
            
            local_dt = dt + timedelta(hours=7)
            months = [
                "января", "февраля", "марта", "апреля", "мая", "июня",
                "июля", "августа", "сентября", "октября", "ноября", "декабря"
            ]
            date_str = f"{local_dt.day} {months[local_dt.month - 1]} {local_dt.year}, {local_dt.hour:02d}:{local_dt.minute:02d}"
        except Exception:
            date_str = ""
    
    report = f"🌍 {location}\n"
    report += f"📅 Прогноз на 7 дней\n"
    if date_str:
        report += f"🕐 Обновлено: {date_str}\n"
    report += "\n"
    
    # Формируем прогноз по каждому дню
    for i, day in enumerate(daily_forecasts, 1):
        date_str = day.get("date_str", "")
        temp_min = day.get("temp_min", 0)
        temp_max = day.get("temp_max", 0)
        temp_avg = day.get("temp_avg", 0)
        description = day.get("description", "нет данных")
        humidity = day.get("humidity_avg", 0)
        wind_speed = day.get("wind_speed_max", 0)
        wind_dir = day.get("wind_direction", "неизвестно")
        
        # Эмодзи для температуры (используем среднюю)
        temp_emoji = _get_temp_emoji(temp_avg)
        
        # Определяем день недели (сегодня, завтра, или дата)
        today = (datetime.now(timezone.utc) + timedelta(hours=7)).date()
        day_date = day.get("date")
        if day_date == today:
            day_label = "Сегодня"
        elif day_date == today + timedelta(days=1):
            day_label = "Завтра"
        else:
            day_label = date_str.split(",")[0] if "," in date_str else date_str
        
        report += f"{temp_emoji} {day_label}\n"
        if day_label not in ["Сегодня", "Завтра"]:
            # Для остальных дней показываем дату отдельной строкой
            report += f"   📅 {date_str}\n"
        report += f"   🌡️ {temp_min}°C ... {temp_max}°C (ср. {temp_avg}°C)\n"
        report += f"   ☁️ {description}\n"
        report += f"   💧 Влажность: {humidity}%\n"
        if wind_speed > 0:
            report += f"   💨 Ветер: до {wind_speed} м/с, {wind_dir}\n"
        else:
            report += f"   💨 Ветер: штиль\n"
        
        # Разделитель между днями (кроме последнего)
        if i < len(daily_forecasts):
            report += "\n"
    
    return report

