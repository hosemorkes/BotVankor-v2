"""
Точка входа приложения.
Инициализация и запуск бота.
"""

import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv
from telegram.ext import Application

from app.bot.telegram.handlers import setup_handlers
from app.database.db import init_db

# Загрузка переменных окружения из .env файла
load_dotenv()


# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
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

