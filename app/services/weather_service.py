"""
Сервис для получения и форматирования данных о погоде.
"""

import logging
from typing import Optional
import aiohttp

logger = logging.getLogger(__name__)


async def get_weather(city: str, api_key: Optional[str] = None) -> Optional[dict]:
    """
    Получает данные о погоде для указанного города.
    
    Args:
        city: Название города
        api_key: API ключ для сервиса погоды (опционально)
    
    Returns:
        Словарь с данными о погоде или None в случае ошибки
    """
    # TODO: реализовать получение погоды через API
    # Пример: OpenWeatherMap, Яндекс.Погода и т.д.
    
    logger.warning("Функция get_weather не реализована")
    return None


def format_weather_report(weather_data: dict) -> str:
    """
    Форматирует данные о погоде для вывода пользователю.
    
    Args:
        weather_data: Данные о погоде из get_weather
    
    Returns:
        Отформатированная строка с информацией о погоде
    """
    # TODO: реализовать форматирование данных о погоде
    return "Информация о погоде будет здесь"

