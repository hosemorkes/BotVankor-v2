"""
Сервис для анализа вероятности вылета вертолёта на основе прогноза погоды.
"""

import logging
import os
import time
from typing import Optional, List, Dict
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

# Координаты Игарки (читаются из .env)
IGARKA_LATITUDE = float(os.getenv("IGARKA_LATITUDE", "67.4"))
IGARKA_LONGITUDE = float(os.getenv("IGARKA_LONGITUDE", "86.6"))
IGARKA_NAME = os.getenv("IGARKA_NAME", "Игарка")

# Длительность кэша по умолчанию (60 минут в секундах)
DEFAULT_CACHE_DURATION = 3600


class FlightForecastCache:
    """
    Класс для кэширования данных прогноза для анализа вылета.
    
    Потокобезопасный кэш с TTL (time-to-live).
    """
    
    def __init__(self, cache_duration: int = DEFAULT_CACHE_DURATION):
        """
        Инициализирует кэш прогноза для вылета.
        
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
_flight_forecast_cache = FlightForecastCache()


def _calculate_risk_score(forecast: dict) -> tuple[int, List[str]]:
    """
    Вычисляет баллы риска для прогноза погоды.
    
    Правила (адаптированы для Крайнего Севера):
    - ветер > 12 м/с → +3 балла
    - порывы > 15 м/с → +3 балла
    - облачность ≥ 80% → +2 балла
    - осадки (снег или сильный дождь) → +2 балла
    - температура ≤ -45°C → +3 балла (экстремальный холод для Крайнего Севера)
    
    Args:
        forecast: Словарь с данными прогноза
    
    Returns:
        Кортеж (баллы риска, список причин)
    """
    score = 0
    reasons = []
    
    wind = forecast.get("wind", {})
    wind_speed = wind.get("speed", 0)
    wind_gust = wind.get("gust", 0)
    
    clouds = forecast.get("clouds", {})
    cloudiness = clouds.get("all", 0)
    
    main = forecast.get("main", {})
    temp = main.get("temp", 0)
    
    rain = forecast.get("rain", {})
    snow = forecast.get("snow", {})
    
    weather_list = forecast.get("weather", [{}])
    weather_main = weather_list[0].get("main", "").lower() if weather_list else ""
    weather_desc = weather_list[0].get("description", "").lower() if weather_list else ""
    
    # Ветер > 12 м/с
    if wind_speed > 12:
        score += 3
        reasons.append(f"💨 Сильный ветер {wind_speed:.1f} м/с")
    
    # Порывы > 15 м/с
    if wind_gust > 15:
        score += 3
        reasons.append(f"🌪️ Порывы ветра до {wind_gust:.1f} м/с")
    
    # Облачность ≥ 80%
    if cloudiness >= 80:
        score += 2
        reasons.append(f"☁️ Плотная облачность {cloudiness}%")
    
    # Осадки (снег или сильный дождь)
    has_snow = (snow and snow.get("3h", 0) > 0) or weather_main == "snow" or "снег" in weather_desc
    has_heavy_rain = (rain and rain.get("3h", 0) > 3) or "сильный" in weather_desc or "ливень" in weather_desc or weather_main == "rain"
    
    if has_snow:
        score += 2
        snow_amount = snow.get("3h", 0) if snow else 0
        if snow_amount > 0:
            reasons.append(f"❄️ Снегопад ({snow_amount:.1f} мм за 3ч)")
        else:
            reasons.append("❄️ Снег")
    elif has_heavy_rain:
        score += 2
        rain_amount = rain.get("3h", 0) if rain else 0
        if rain_amount > 3:
            reasons.append(f"🌧️ Сильный дождь ({rain_amount:.1f} мм за 3ч)")
        else:
            reasons.append("🌧️ Сильный дождь")
    
    # Температура ≤ -45°C (экстремальный холод для Крайнего Севера)
    if temp <= -45:
        score += 3
        reasons.append(f"🥶 Экстремальный холод {temp:.0f}°C")
    
    return score, reasons


def _get_risk_status(score: int) -> tuple[str, str]:
    """
    Определяет статус риска на основе баллов.
    
    Args:
        score: Баллы риска
    
    Returns:
        Кортеж (статус, эмодзи)
    """
    if score <= 3:
        return "✅ Вылет возможен", "✅"
    elif score <= 6:
        return "⚠️ Осторожно — шанс задержки", "⚠️"
    else:
        return "❌ Вылет НЕ рекомендуется", "❌"


def _get_humorous_comment(score: int, reasons: List[str]) -> str:
    """
    Генерирует юмористический комментарий на основе баллов риска.
    
    Args:
        score: Баллы риска
        reasons: Список причин риска
    
    Returns:
        Юмористический комментарий
    """
    if score <= 3:
        comments = [
            "Пилоты будут в восторге! 🌟 Ни ветра, ни туч — как блядь праздник! 🥳",
            "Погодка охуенная — можно рвануть! ✈️ (Даже тучи в отпуске) 😎",
            "Ни хрена не мешает — лети, как на шашлыки! 🚁🔥",
            "Погода лучше, чем у твоей тёщи настроение! 😂☀️",
            "Ветер такой слабый, что муха обделалась бы до земли доползла! 🪰💨",
            "Сейчас полетишь и даже глушитель не перегреется! 😈🚁",
            "Погодка ровная, как твой последний понт — лети! 😏✈️",
            "Какая-то хуйня тут называется идеальная погода! 😅☀️",
            "Такие условия, что даже твоя бывшая не испортит! 🤣💨",
            "Ветер такой тихий, что даже твой крик не услышит! 🙉🚁",
            # Скороговорки-перевёртыши с матом и чёрным юмором:
            "Ехал Грека через реку, видит — реку ветер сгреб… и хуй там плавал! 😤🌬️", 
            "На дворе трава, на траве дрова — и чёрт знает куда ветер их занёс! 🌾🔥😈",
            "Тридцать три корабля лавировали, лавировали — да хрен их вылавировали! 🚢😂",
            "У ежа ежата, у ужа ужата — но ни один не улетел, потому что ветра нет! 🦔🤦‍♂️",
            "Бык тупогуб, тупогубенький бычок — а ветер такой хуй, что и быка не подвинул! 🐂💨",
            "Купи кипу пуха, купи кипу пик — но на вертолёт это никак не влияет! 🧨😆",
        ]
    elif score <= 6:
        comments = [
            "Может быть, а может и не быть… 🤷 Блядь, как повезёт, как ветер перемен! 🌪️",
            "Пилоты будут думать дважды! 🤔 А мы ещё сильнее — решай сам, козёл! 😄",
            "Шанс 50/50 — как подбросить монетку, только если выпадет решка, то вертолёт улетит без нас! 🪙😅",
            "Не самое лучшее время, но можно рискнуть… Если ты хочешь стать мемом! 📸💀",
            "Условия такие, что даже чайнику страшно — и ты ещё хочешь полететь? 🫖🔥",
            "Погодка как в аду: блядь, жарко-холодно, ветер шалит… но не убивает! 😈🌬️",
            "Как сказать… типа летать можно, если ты не против пару гвоздей забить! 🔨😆",
            "Ветер гуляет как псих в тюрьме — не смертельно, но зверски мешает! 🐺💨",
            "Нормально вроде, но чёрт побери, что будет через час — никто не знает! 🕐😵",
            "Погодка как старая свидомая шутка — вроде смешно, но можешь поплатиться! 🤡☁️",
        ]
    else:
        comments = [
            "Лучше остаться дома и пить чай! ☕ А вертолёт пусть сам решает, жить или нет… 😵‍💫",
            "Даже вертолёт подумает дважды! 🤯 Он же не долбоёб, чтобы в такую жопу лезть! 😤",
            "Пилоты уже готовят оправдания! 📝 ‘Это не я, это погода такой мудак…’ 😂",
            "Матушка-природа говорит 'НЕТ'! 🌪️ И добавляет: ‘Пошёл ты…’ 💀",
            "Шансы на вылет: как найти иголку в стоге сена! 🪡 А иголка ещё и с динамитом! 💣",
            "Такая погода, что даже твой труп хотел бы остаться в тёплой каюте… но не может! ☠️🔥",
            "Сегодня вылет — это как хуйню на стену пукнуть: эффект тот же, но чёрт знает зачем! 🤡💨",
            "Погодные условия — пиздец полный, как у тебя в голове после третьей смены… 🤯🌫️",
            "Вылет сегодня — это как попытка обнять акулу: возможно, но нахрена? 🦈😆",
            "Ты лучше кота погладь, он умнее этих метео-чёртов… 😼🌧️",
        ]
    
    import random
    return random.choice(comments)


async def get_flight_forecast(
    api_key: Optional[str] = None,
    cache: Optional[FlightForecastCache] = None
) -> Optional[dict]:
    """
    Получает прогноз погоды на 3 дня для анализа вероятности вылета.
    
    Получает прогноз для Ванкора и Игарки, анализирует условия для каждого дня.
    
    Args:
        api_key: API ключ для OpenWeatherMap (если не указан, берётся из переменных окружения)
        cache: Экземпляр FlightForecastCache для кэширования (если не указан, используется глобальный)
    
    Returns:
        Словарь с данными анализа или None в случае ошибки
    """
    # Используем переданный кэш или глобальный
    forecast_cache = cache if cache is not None else _flight_forecast_cache
    
    # Проверяем кэш
    cached_data = forecast_cache.get()
    if cached_data is not None:
        logger.debug("Возвращаем данные прогноза вылета из кэша")
        return cached_data
    
    # Получаем API ключ
    if not api_key:
        api_key = os.getenv("WEATHER_API_KEY")
    
    if not api_key:
        logger.error("WEATHER_API_KEY не установлен в переменных окружения")
        return None
    
    try:
        # Получаем прогноз для Ванкора
        vankor_url = (
            f"https://api.openweathermap.org/data/2.5/forecast"
            f"?lat={VANKOR_LATITUDE}&lon={VANKOR_LONGITUDE}"
            f"&appid={api_key}&units=metric&lang=ru&cnt=24"
        )
        
        # Получаем прогноз для Игарки
        igarka_url = (
            f"https://api.openweathermap.org/data/2.5/forecast"
            f"?lat={IGARKA_LATITUDE}&lon={IGARKA_LONGITUDE}"
            f"&appid={api_key}&units=metric&lang=ru&cnt=24"
        )
        
        async with aiohttp.ClientSession() as session:
            # Запрашиваем оба прогноза параллельно
            async with session.get(vankor_url, timeout=aiohttp.ClientTimeout(total=15)) as vankor_response, \
                     session.get(igarka_url, timeout=aiohttp.ClientTimeout(total=15)) as igarka_response:
                
                if vankor_response.status == 200 and igarka_response.status == 200:
                    vankor_data = await vankor_response.json()
                    igarka_data = await igarka_response.json()
                    
                    # Группируем прогнозы по дням для обоих локаций
                    vankor_daily = _group_forecasts_by_day(vankor_data.get("list", []), VANKOR_NAME)
                    igarka_daily = _group_forecasts_by_day(igarka_data.get("list", []), IGARKA_NAME)
                    
                    # Анализируем каждый день
                    daily_analyses = []
                    for i in range(min(3, len(vankor_daily), len(igarka_daily))):
                        vankor_day = vankor_daily[i]
                        igarka_day = igarka_daily[i]
                        
                        # Вычисляем баллы риска для обеих локаций
                        vankor_score, vankor_reasons = _calculate_risk_score(vankor_day.get("worst_forecast", {}))
                        igarka_score, igarka_reasons = _calculate_risk_score(igarka_day.get("worst_forecast", {}))
                        
                        # Берем максимальный балл (худший сценарий)
                        max_score = max(vankor_score, igarka_score)
                        all_reasons = list(set(vankor_reasons + igarka_reasons))  # Убираем дубликаты
                        
                        status, status_emoji = _get_risk_status(max_score)
                        comment = _get_humorous_comment(max_score, all_reasons)
                        
                        daily_analyses.append({
                            "date": vankor_day.get("date"),
                            "date_str": vankor_day.get("date_str", ""),
                            "vankor": vankor_day,
                            "igarka": igarka_day,
                            "risk_score": max_score,
                            "reasons": all_reasons,
                            "status": status,
                            "status_emoji": status_emoji,
                            "comment": comment
                        })
                    
                    # Формируем структурированные данные
                    forecast_data = {
                        "vankor_location": VANKOR_NAME,
                        "igarka_location": IGARKA_NAME,
                        "daily_analyses": daily_analyses,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    
                    # Сохраняем в кэш
                    forecast_cache.set(forecast_data)
                    
                    logger.info(f"Получен анализ вероятности вылета на {len(daily_analyses)} дней")
                    return forecast_data
                else:
                    vankor_status = vankor_response.status if vankor_response.status != 200 else None
                    igarka_status = igarka_response.status if igarka_response.status != 200 else None
                    logger.error(f"Ошибка API прогноза погоды: Ванкор={vankor_status}, Игарка={igarka_status}")
                    return None
                    
    except aiohttp.ClientError as e:
        logger.error(f"Ошибка сети при запросе прогноза погоды: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении прогноза погоды: {e}")
        return None


def _group_forecasts_by_day(forecast_list: List[dict], location_name: str) -> List[dict]:
    """
    Группирует прогнозы по дням и находит худший прогноз для каждого дня.
    
    Args:
        forecast_list: Список прогнозов из API (каждые 3 часа)
        location_name: Название локации
    
    Returns:
        Список словарей с прогнозами по дням
    """
    # Группируем по дням
    daily_data = defaultdict(list)
    
    # Конвертируем UTC в локальное время (UTC+7)
    timezone_offset = timedelta(hours=7)
    
    for forecast in forecast_list:
        # Парсим timestamp
        dt_utc = datetime.fromtimestamp(forecast["dt"], tz=timezone.utc)
        dt_local = dt_utc + timezone_offset
        date_key = dt_local.date()
        
        daily_data[date_key].append(forecast)
    
    # Формируем итоговые данные по дням
    daily_forecasts = []
    for date_key in sorted(daily_data.keys())[:3]:  # Берем максимум 3 дня
        day_forecasts = daily_data[date_key]
        
        # Находим худший прогноз (с максимальным ветром, облачностью и т.д.)
        worst_forecast = max(day_forecasts, key=lambda f: (
            f.get("wind", {}).get("speed", 0),
            f.get("wind", {}).get("gust", 0),
            f.get("clouds", {}).get("all", 0)
        ))
        
        # Вычисляем средние значения для отображения
        temps = [f.get("main", {}).get("temp", 0) for f in day_forecasts]
        wind_speeds = [f.get("wind", {}).get("speed", 0) for f in day_forecasts]
        cloudiness = [f.get("clouds", {}).get("all", 0) for f in day_forecasts]
        
        daily_forecast = {
            "date": date_key,
            "date_str": _format_date(date_key),
            "location": location_name,
            "temp_avg": round(sum(temps) / len(temps)) if temps else 0,
            "temp_min": round(min(temps)) if temps else 0,
            "temp_max": round(max(temps)) if temps else 0,
            "wind_speed_max": round(max(wind_speeds), 1) if wind_speeds else 0,
            "wind_gust_max": round(max([f.get("wind", {}).get("gust", 0) for f in day_forecasts]), 1),
            "cloudiness_max": max(cloudiness) if cloudiness else 0,
            "worst_forecast": worst_forecast
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


def format_flight_forecast_report(forecast_data: dict) -> str:
    """
    Форматирует анализ вероятности вылета для вывода пользователю.
    
    Args:
        forecast_data: Данные анализа из get_flight_forecast
    
    Returns:
        Отформатированная строка с анализом вероятности вылета
    """
    if not forecast_data or not forecast_data.get("daily_analyses"):
        return "❌ Не удалось получить анализ вероятности вылета. Попробуйте позже."
    
    vankor_location = forecast_data.get("vankor_location", "Ванкор")
    igarka_location = forecast_data.get("igarka_location", "Игарка")
    daily_analyses = forecast_data.get("daily_analyses", [])
    
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
    
    report = f"🚁 Вероятность вылета вертолёта\n"
    report += f"📍 Маршрут: {vankor_location} ↔ {igarka_location}\n"
    report += f"📅 Прогноз на 3 дня\n"
    if date_str:
        report += f"🕐 Обновлено: {date_str}\n"
    report += "\n"
    
    # Определяем сегодняшний день
    today = (datetime.now(timezone.utc) + timedelta(hours=7)).date()
    
    # Формируем анализ по каждому дню
    for i, analysis in enumerate(daily_analyses, 1):
        date_str = analysis.get("date_str", "")
        day_date = analysis.get("date")
        risk_score = analysis.get("risk_score", 0)
        reasons = analysis.get("reasons", [])
        status = analysis.get("status", "")
        status_emoji = analysis.get("status_emoji", "❓")
        comment = analysis.get("comment", "")
        
        vankor_day = analysis.get("vankor", {})
        igarka_day = analysis.get("igarka", {})
        
        # Определяем день недели (сегодня, завтра, или дата)
        if day_date == today:
            day_label = "Сегодня"
        elif day_date == today + timedelta(days=1):
            day_label = "Завтра"
        else:
            day_label = date_str.split(",")[0] if "," in date_str else date_str
        
        report += f"{status_emoji} {day_label}\n"
        if day_label not in ["Сегодня", "Завтра"]:
            report += f"📅 {date_str}\n"
        
        report += f"\n{status}\n"
        report += f"🎯 Баллы риска: {risk_score}/13\n\n"
        
        # Погодные условия
        report += f"🌍 {vankor_location}:\n"
        report += f"   🌡️ {vankor_day.get('temp_min', 0)}°C ... {vankor_day.get('temp_max', 0)}°C\n"
        report += f"   💨 Ветер: до {vankor_day.get('wind_speed_max', 0)} м/с"
        if vankor_day.get('wind_gust_max', 0) > 0:
            report += f" (порывы до {vankor_day.get('wind_gust_max', 0)} м/с)"
        report += "\n"
        report += f"   ☁️ Облачность: до {vankor_day.get('cloudiness_max', 0)}%\n"
        
        report += f"\n🌍 {igarka_location}:\n"
        report += f"   🌡️ {igarka_day.get('temp_min', 0)}°C ... {igarka_day.get('temp_max', 0)}°C\n"
        report += f"   💨 Ветер: до {igarka_day.get('wind_speed_max', 0)} м/с"
        if igarka_day.get('wind_gust_max', 0) > 0:
            report += f" (порывы до {igarka_day.get('wind_gust_max', 0)} м/с)"
        report += "\n"
        report += f"   ☁️ Облачность: до {igarka_day.get('cloudiness_max', 0)}%\n"
        
        # Причины риска
        if reasons:
            report += f"\n⚠️ Причины риска:\n"
            for reason in reasons:
                report += f"   • {reason}\n"
        
        # Юмористический комментарий
        report += f"\n{comment}\n"
        
        # Разделитель между днями (кроме последнего)
        if i < len(daily_analyses):
            report += "\n" + "─" * 30 + "\n\n"
    
    return report

