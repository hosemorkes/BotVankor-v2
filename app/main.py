"""
Точка входа приложения.
Инициализация и запуск бота.
"""

import asyncio
import logging
import re
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram.ext import Application

from app.bot.telegram.handlers import setup_handlers
from app.database.db import init_db

# Загрузка переменных окружения из .env файла
load_dotenv()


class TokenMaskingFormatter(logging.Formatter):
    """Форматтер для маскировки токенов бота в логах."""
    
    def __init__(self, fmt=None, datefmt=None):
        super().__init__(fmt, datefmt)
        # Получаем токен для маскировки
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if self.token:
            # Создаём паттерн для замены токена в URL
            # Маскируем токен в URL вида /bot<TOKEN>/...
            self.token_pattern = re.compile(
                r'/bot' + re.escape(self.token) + r'([/:])',
                re.IGNORECASE
            )
    
    def format(self, record):
        """Форматирует запись лога с маскировкой токена."""
        # Форматируем запись стандартным способом
        message = super().format(record)
        
        # Маскируем токен в финальном сообщении
        if self.token:
            message = self.token_pattern.sub(r'/bot***\1', message)
        
        return message


# Настройка логирования с кастомным форматтером
token_formatter = TokenMaskingFormatter(
    fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Получаем корневой обработчик и применяем форматтер
root_handler = logging.StreamHandler()
root_handler.setFormatter(token_formatter)

# Настраиваем корневой логгер
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(root_handler)

# Также применяем форматтер к логгеру httpx
httpx_logger = logging.getLogger("httpx")
for handler in httpx_logger.handlers:
    handler.setFormatter(token_formatter)
if not httpx_logger.handlers:
    httpx_handler = logging.StreamHandler()
    httpx_handler.setFormatter(token_formatter)
    httpx_logger.addHandler(httpx_handler)

logger = logging.getLogger(__name__)


async def initialize_bot_with_retry(token: str, proxy_url: str = None, max_retries: int = 5, retry_delay: int = 10) -> Application:
    """
    Инициализирует приложение бота с автоматическим retry.

    Args:
        token: Токен Telegram бота
        proxy_url: URL прокси для подключения к Telegram API (опционально)
        max_retries: Максимальное количество попыток
        retry_delay: Задержка между попытками (секунды)

    Returns:
        Инициализированное приложение Application

    Raises:
        RuntimeError: Если не удалось подключиться после всех попыток
    """
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Попытка подключения к Telegram API ({attempt}/{max_retries})...")

            # Создание приложения с увеличенными таймаутами
            builder = (
                Application.builder()
                .token(token)
                .read_timeout(30)
                .write_timeout(30)
                .connect_timeout(30)
                .pool_timeout(30)
            )

            # Применение прокси, если указан
            if proxy_url:
                builder = builder.proxy(proxy_url).get_updates_proxy(proxy_url)
                logger.info(f"✓ Прокси включен: {proxy_url.split('@')[0]}://***")

            application = builder.build()

            # Настройка обработчиков
            setup_handlers(application)

            # Инициализация (это проверяет токен и подключение)
            await application.initialize()
            logger.info("✅ Успешное подключение к Telegram API")

            return application

        except Exception as e:
            logger.error(f"❌ Ошибка подключения (попытка {attempt}/{max_retries}): {e}")

            if attempt < max_retries:
                logger.info(f"⏳ Ожидание {retry_delay} секунд перед повтором...")
                await asyncio.sleep(retry_delay)
            else:
                raise RuntimeError(
                    f"Не удалось подключиться к Telegram API после {max_retries} попыток. "
                    f"Проверьте:\n"
                    f"1. Корректность TELEGRAM_BOT_TOKEN в .env\n"
                    f"2. Доступность сервера (файрвол, DNS)\n"
                    f"3. Подключение к интернету"
                ) from e


async def main_async() -> None:
    """Асинхронная функция запуска бота."""
    # Инициализация базы данных
    db_path = Path("data/bot.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(str(db_path))

    # Получение токена из переменных окружения
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения")

    # Получение URL прокси (опционально)
    proxy_url = os.getenv("PROXY_URL")

    # Инициализация приложения с retry логикой
    application = await initialize_bot_with_retry(token, proxy_url=proxy_url)

    # Запуск бота через контекстный менеджер
    async with application:
        logger.info("🚀 Бот запущен и готов к работе")
        await application.start()
        await application.updater.start_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True
        )

        # Ожидание остановки (бесконечный цикл до KeyboardInterrupt)
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Получен сигнал остановки")
        finally:
            await application.updater.stop()
            await application.stop()
            await application.shutdown()


def main() -> None:
    """Основная функция запуска бота."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")


if __name__ == "__main__":
    main()

