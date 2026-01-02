"""
Тесты для работы с базой данных.
"""

import pytest
import tempfile
import os

from app.database.db import init_db, get_session, UserCRUD, SalaryCRUD, User


@pytest.fixture
def temp_db():
    """Создаёт временную базу данных для тестов."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_db(path)
    yield path
    os.unlink(path)


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
    
    # Проверяем, что повторный вызов возвращает того же пользователя
    user2 = UserCRUD.get_or_create(session, telegram_id=12345)
    assert user2.id == user.id
    
    session.close()


def test_salary_crud_create(temp_db):
    """Тест создания записи о зарплате."""
    session = get_session()
    
    # Создаём пользователя
    user = UserCRUD.get_or_create(session, telegram_id=12345)
    
    # Создаём запись о зарплате
    record = SalaryCRUD.create(
        session,
        user_id=user.id,
        base_salary=1000.0,
        hours_worked=160.0,
        bonus=20000.0,
        gross=160000.0,
        tax=23400.0,
        net=156600.0
    )
    
    assert record.user_id == user.id
    assert record.base_salary == 1000.0
    assert record.net == 156600.0
    
    session.close()

