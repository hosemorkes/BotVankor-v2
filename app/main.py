"""
Точка входа приложения.
Инициализация и запуск бота.
"""

import asyncio
import logging
from pathlib import Path

from telegram import Bot
from telegram.ext import Application

from app.bot.telegram.handlers import setup_handlers
from app.database.db import init_db


# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Основная функция запуска бота."""
    # Инициализация базы данных
    db_path = Path("data/bot.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(str(db_path))
    
    # Получение токена из переменных окружения
    import os
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения")
    
    # Создание приложения
    application = Application.builder().token(token).build()
    
    # Настройка обработчиков
    setup_handlers(application)
    
    # Запуск бота
    logger.info("Бот запущен")
    await application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())

