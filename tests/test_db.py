"""
Тесты для работы с базой данных.
"""

import pytest
import tempfile
import os

from app.database.db import (
    init_db, get_session, UserCRUD, SalaryCRUD, WeatherCRUD, User,
    SalaryRecord, WeatherRecord
)
from sqlalchemy.exc import SQLAlchemyError


@pytest.fixture
def temp_db():
    """Создаёт временную базу данных для тестов."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    # Закрываем все сессии перед удалением файла
    try:
        session = get_session()
        session.close()
    except:
        pass
    # Небольшая задержка для Windows
    import time
    time.sleep(0.1)
    try:
        os.unlink(path)
    except PermissionError:
        # Игнорируем ошибку на Windows, файл будет удалён позже
        pass


def test_user_crud_get_or_create(temp_db):
    """Тест создания и получения пользователя."""
    session = get_session()
    
    user = UserCRUD.get_or_create(
        session,
        telegram_id=12345,
        username="test_user",
        first_name="Test"
    )
    
    assert user.telegram_id == 12345
    assert user.username == "test_user"
    assert user.first_name == "Test"
    
    # Проверяем, что повторный вызов возвращает того же пользователя (не создаёт дубликат)
    user2 = UserCRUD.get_or_create(session, telegram_id=12345)
    assert user2.id == user.id
    assert user2.telegram_id == user.telegram_id
    
    # Проверяем, что все пользователи уникальны по telegram_id
    all_users = session.query(User).all()
    telegram_ids = [u.telegram_id for u in all_users]
    assert len(telegram_ids) == len(set(telegram_ids)), "Обнаружены дубликаты пользователей"
    
    session.close()


def test_user_crud_no_duplicates(temp_db):
    """Тест, что повторный /start не создаёт дубликат пользователя."""
    session = get_session()
    
    # Первый вызов - создаём пользователя
    user1 = UserCRUD.get_or_create(
        session,
        telegram_id=99999,
        username="duplicate_test",
        first_name="First"
    )
    user1_id = user1.id
    
    # Второй вызов - должен вернуть того же пользователя
    user2 = UserCRUD.get_or_create(
        session,
        telegram_id=99999,
        username="duplicate_test",
        first_name="First"
    )
    
    # Проверяем, что это тот же пользователь
    assert user2.id == user1_id
    assert user2.telegram_id == user1.telegram_id
    
    # Проверяем, что в БД только один пользователь с этим telegram_id
    users_with_id = session.query(User).filter_by(telegram_id=99999).all()
    assert len(users_with_id) == 1, f"Найдено {len(users_with_id)} пользователей вместо 1"
    
    session.close()


def test_salary_crud_create(temp_db):
    """Тест создания записи о зарплате."""
    session = get_session()
    
    # Создаём пользователя
    user = UserCRUD.get_or_create(session, telegram_id=12345)
    
    # Создаём запись о зарплате
    record = SalaryCRUD.create(
        session=session,
        user_id=user.id,
        base_salary=1000.0,
        hours_worked=160.0,
        gross=160000.0,
        gross_with_coefficient=160000.0,
        total=180000.0,
        tax=23400.0,
        net=156600.0,
        bonus=20000.0
    )
    
    assert record.user_id == user.id
    assert record.base_salary == 1000.0
    assert record.net == 156600.0
    
    session.close()


def test_db_repeated_init(temp_db):
    """Тест, что повторная инициализация не ломает БД."""
    # Первая инициализация уже выполнена в фикстуре
    # Создаём пользователя
    session1 = get_session()
    user1 = UserCRUD.get_or_create(session1, telegram_id=11111, first_name="Test1")
    session1.close()
    
    # Повторная инициализация
    init_db(temp_db)
    
    # Проверяем, что данные сохранились
    session2 = get_session()
    user2 = UserCRUD.get_by_telegram_id(session2, telegram_id=11111)
    assert user2 is not None
    assert user2.first_name == "Test1"
    session2.close()


def test_db_connection(temp_db):
    """Тест подключения к БД."""
    session = get_session()
    assert session is not None
    
    # Проверяем, что можем выполнить запрос
    from sqlalchemy import text
    result = session.execute(text("SELECT 1"))
    assert result.scalar() == 1
    
    session.close()


def test_tables_exist(temp_db):
    """Тест, что все таблицы созданы."""
    session = get_session()
    from sqlalchemy import inspect
    
    inspector = inspect(session.bind)
    tables = inspector.get_table_names()
    
    assert "users" in tables
    assert "salary_records" in tables
    assert "weather_records" in tables
    
    session.close()


def test_user_crud_error_handling(temp_db):
    """Тест обработки ошибок в CRUD операциях."""
    session = get_session()
    
    # Попытка создать пользователя с дублирующимся telegram_id
    UserCRUD.get_or_create(session, telegram_id=22222, first_name="Test")
    
    # Вторая попытка с тем же ID должна вернуть существующего пользователя
    user2 = UserCRUD.get_or_create(session, telegram_id=22222, first_name="Test2")
    assert user2.first_name == "Test2"  # Данные обновятся
    
    session.close()


def test_salary_crud_get_records(temp_db):
    """Тест получения записей о зарплате."""
    session = get_session()
    
    # Создаём пользователя
    user = UserCRUD.get_or_create(session, telegram_id=33333)
    
    # Создаём несколько записей
    SalaryCRUD.create(
        session=session,
        user_id=user.id,
        base_salary=1000.0,
        hours_worked=160.0,
        gross=160000.0,
        gross_with_coefficient=160000.0,
        total=160000.0,
        tax=20800.0,
        net=139200.0,
        bonus=0.0
    )
    SalaryCRUD.create(
        session=session,
        user_id=user.id,
        base_salary=1000.0,
        hours_worked=160.0,
        gross=160000.0,
        gross_with_coefficient=160000.0,
        total=180000.0,
        tax=23400.0,
        net=156600.0,
        bonus=20000.0
    )
    
    # Получаем записи
    records = SalaryCRUD.get_user_records(session, user.id, limit=5)
    assert len(records) == 2
    assert records[0].net == 156600.0  # Последняя запись первая
    
    session.close()


def test_weather_crud_create(temp_db):
    """Тест создания записи о погоде."""
    session = get_session()
    
    # Создаём пользователя
    user = UserCRUD.get_or_create(session, telegram_id=44444)
    
    # Создаём запись о погоде
    record = WeatherCRUD.create(
        session,
        user_id=user.id,
        city="Москва",
        weather_data='{"temp": 20, "description": "ясно"}'
    )
    
    assert record.user_id == user.id
    assert record.city == "Москва"
    assert "temp" in record.weather_data
    
    session.close()

