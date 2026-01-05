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


async def main_async() -> None:
    """Асинхронная функция запуска бота."""
    # Инициализация базы данных
    db_path = Path("data/bot.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(str(db_path))
    
    # Получение токена из переменных окружения
    import os
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения")
    
    # Создание приложения с увеличенными таймаутами
    application = (
        Application.builder()
        .token(token)
        .read_timeout(30)  # Увеличиваем таймаут чтения до 30 секунд
        .write_timeout(30)  # Увеличиваем таймаут записи до 30 секунд
        .connect_timeout(30)  # Увеличиваем таймаут подключения до 30 секунд
        .pool_timeout(30)  # Увеличиваем таймаут пула до 30 секунд
        .build()
    )
    
    # Настройка обработчиков
    setup_handlers(application)
    
    # Запуск бота через контекстный менеджер
    async with application:
        logger.info("Бот запущен")
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

