"""
Тесты для конфигурации прокси бота.
"""

import pytest
import os
from unittest.mock import patch, AsyncMock, MagicMock
from app.main import initialize_bot_with_retry


@pytest.mark.asyncio
async def test_bot_proxy_configuration_with_proxy():
    """Тест, что ApplicationBuilder правильно применяет прокси URL."""
    test_token = "test_token_123"
    test_proxy = "socks5://testproxy:1080"

    # Мокируем Application.builder() и его методы
    with patch('app.main.Application') as mock_app_class:
        mock_builder = MagicMock()
        mock_application = AsyncMock()

        # Настраиваем цепочку методов builder
        mock_builder.token.return_value = mock_builder
        mock_builder.read_timeout.return_value = mock_builder
        mock_builder.write_timeout.return_value = mock_builder
        mock_builder.connect_timeout.return_value = mock_builder
        mock_builder.pool_timeout.return_value = mock_builder
        mock_builder.proxy.return_value = mock_builder
        mock_builder.get_updates_proxy.return_value = mock_builder
        mock_builder.build.return_value = mock_application

        mock_app_class.builder.return_value = mock_builder

        # Мокируем setup_handlers и initialize
        with patch('app.main.setup_handlers'):
            mock_application.initialize = AsyncMock()

            # Вызываем функцию инициализации с прокси
            result = await initialize_bot_with_retry(
                token=test_token,
                proxy_url=test_proxy,
                max_retries=1
            )

        # Проверяем, что proxy() и get_updates_proxy() были вызваны с правильным URL
        mock_builder.proxy.assert_called_once_with(test_proxy)
        mock_builder.get_updates_proxy.assert_called_once_with(test_proxy)

        # Проверяем, что build() был вызван
        mock_builder.build.assert_called_once()

        # Проверяем, что приложение инициализировано
        mock_application.initialize.assert_called_once()


@pytest.mark.asyncio
async def test_bot_proxy_configuration_without_proxy():
    """Тест, что ApplicationBuilder работает без прокси."""
    test_token = "test_token_456"

    # Мокируем Application.builder() и его методы
    with patch('app.main.Application') as mock_app_class:
        mock_builder = MagicMock()
        mock_application = AsyncMock()

        # Настраиваем цепочку методов builder
        mock_builder.token.return_value = mock_builder
        mock_builder.read_timeout.return_value = mock_builder
        mock_builder.write_timeout.return_value = mock_builder
        mock_builder.connect_timeout.return_value = mock_builder
        mock_builder.pool_timeout.return_value = mock_builder
        mock_builder.proxy.return_value = mock_builder
        mock_builder.get_updates_proxy.return_value = mock_builder
        mock_builder.build.return_value = mock_application

        mock_app_class.builder.return_value = mock_builder

        # Мокируем setup_handlers и initialize
        with patch('app.main.setup_handlers'):
            mock_application.initialize = AsyncMock()

            # Вызываем функцию инициализации БЕЗ прокси
            result = await initialize_bot_with_retry(
                token=test_token,
                proxy_url=None,
                max_retries=1
            )

        # Проверяем, что proxy() и get_updates_proxy() НЕ были вызваны
        mock_builder.proxy.assert_not_called()
        mock_builder.get_updates_proxy.assert_not_called()

        # Проверяем, что build() был вызван
        mock_builder.build.assert_called_once()

        # Проверяем, что приложение инициализировано
        mock_application.initialize.assert_called_once()


@pytest.mark.asyncio
async def test_main_async_reads_proxy_from_env():
    """Тест, что main_async читает PROXY_URL из переменных окружения."""
    test_proxy = "socks5://env_proxy:1080"

    # Мокируем переменные окружения и функции
    with patch.dict(os.environ, {
        "TELEGRAM_BOT_TOKEN": "test_token",
        "PROXY_URL": test_proxy
    }):
        with patch('app.main.init_db'):
            with patch('app.main.initialize_bot_with_retry') as mock_init:
                mock_init.return_value = AsyncMock()

                # Импортируем после установки переменных окружения
                from app.main import main_async

                # Нам нужно остановить бесконечный цикл, поэтому мокируем его
                with patch('asyncio.sleep', side_effect=KeyboardInterrupt):
                    try:
                        await main_async()
                    except KeyboardInterrupt:
                        pass

                # Проверяем, что initialize_bot_with_retry был вызван с прокси
                calls = mock_init.call_args_list
                assert len(calls) > 0
                # Проверяем, что proxy_url был передан
                assert 'proxy_url' in calls[0].kwargs or len(calls[0].args) > 1


def test_proxy_url_in_env_example():
    """Тест, что .env.example содержит PROXY_URL."""
    # Ищем .env.example в текущей или родительской директории
    import pathlib
    env_example_path = pathlib.Path(__file__).parent.parent / ".env.example"

    # Проверяем, что файл существует
    assert env_example_path.exists(), f"Файл {env_example_path} не найден"

    # Читаем содержимое
    content = env_example_path.read_text(encoding='utf-8')

    # Проверяем наличие переменных Shadowsocks
    assert "SS_SERVER" in content, "SS_SERVER не найден в .env.example"
    assert "SS_PORT" in content, "SS_PORT не найден в .env.example"
    assert "SS_PASSWORD" in content, "SS_PASSWORD не найден в .env.example"
    assert "SS_METHOD" in content, "SS_METHOD не найден в .env.example"
    assert "PROXY_URL" in content, "PROXY_URL не найден в .env.example"
    assert "socks5" in content.lower(), "socks5 не найден в .env.example"
