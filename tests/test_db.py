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

