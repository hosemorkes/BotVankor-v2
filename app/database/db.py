"""
ORM-модели, CRUD операции и инициализация базы данных.
"""

import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

Base = declarative_base()


# ORM модели
class User(Base):
    """Модель пользователя."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(100))
    first_name = Column(String(100))
    last_name = Column(String(100))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class SalaryRecord(Base):
    """Модель записи о зарплате."""
    __tablename__ = "salary_records"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    base_salary = Column(Float, nullable=False)
    hours_worked = Column(Float, nullable=False)
    bonus = Column(Float, default=0.0)
    gross = Column(Float, nullable=False)
    tax = Column(Float, nullable=False)
    net = Column(Float, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class WeatherRecord(Base):
    """Модель записи о запросе погоды."""
    __tablename__ = "weather_records"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    city = Column(String(100), nullable=False)
    weather_data = Column(Text)  # JSON строка с данными о погоде
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# CRUD операции
class UserCRUD:
    """CRUD операции для пользователей."""
    
    @staticmethod
    def get_or_create(session: Session, telegram_id: int, username: Optional[str] = None,
                     first_name: Optional[str] = None, last_name: Optional[str] = None) -> User:
        """
        Получить или создать пользователя.
        
        Если пользователь существует, обновляет его данные (username, имя).
        Если не существует - создаёт нового.
        
        Args:
            session: Сессия БД
            telegram_id: Telegram ID пользователя
            username: Username пользователя (опционально)
            first_name: Имя пользователя (опционально)
            last_name: Фамилия пользователя (опционально)
        
        Returns:
            Объект User (существующий или новый)
        """
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if not user:
            # Создаём нового пользователя
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            session.add(user)
            session.commit()
            logger.info(f"Создан новый пользователь в БД: telegram_id={telegram_id}")
        else:
            # Обновляем данные существующего пользователя (если изменились)
            updated = False
            if user.username != username:
                user.username = username
                updated = True
            if user.first_name != first_name:
                user.first_name = first_name
                updated = True
            if user.last_name != last_name:
                user.last_name = last_name
                updated = True
            
            if updated:
                session.commit()
                logger.debug(f"Обновлены данные пользователя: telegram_id={telegram_id}")
        
        return user
    
    @staticmethod
    def get_by_telegram_id(session: Session, telegram_id: int) -> Optional[User]:
        """Получить пользователя по Telegram ID."""
        return session.query(User).filter_by(telegram_id=telegram_id).first()


class SalaryCRUD:
    """CRUD операции для записей о зарплате."""
    
    @staticmethod
    def create(session: Session, user_id: int, base_salary: float, hours_worked: float,
              bonus: float, gross: float, tax: float, net: float) -> SalaryRecord:
        """Создать запись о зарплате."""
        record = SalaryRecord(
            user_id=user_id,
            base_salary=base_salary,
            hours_worked=hours_worked,
            bonus=bonus,
            gross=gross,
            tax=tax,
            net=net
        )
        session.add(record)
        session.commit()
        return record
    
    @staticmethod
    def get_user_records(session: Session, user_id: int, limit: int = 10) -> list[SalaryRecord]:
        """Получить последние записи пользователя."""
        return session.query(SalaryRecord).filter_by(user_id=user_id)\
            .order_by(SalaryRecord.created_at.desc()).limit(limit).all()


class WeatherCRUD:
    """CRUD операции для записей о погоде."""
    
    @staticmethod
    def create(session: Session, user_id: int, city: str, weather_data: str) -> WeatherRecord:
        """Создать запись о запросе погоды."""
        record = WeatherRecord(
            user_id=user_id,
            city=city,
            weather_data=weather_data
        )
        session.add(record)
        session.commit()
        return record


# Инициализация базы данных
_engine: Optional[object] = None
_SessionLocal: Optional[sessionmaker] = None


def init_db(db_path: str) -> None:
    """
    Инициализирует базу данных и создаёт таблицы.
    
    Args:
        db_path: Путь к файлу базы данных
    """
    global _engine, _SessionLocal
    
    # Создаём директорию для БД если её нет
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Создаём движок SQLAlchemy
    _engine = create_engine(f"sqlite:///{db_path}", echo=False)
    _SessionLocal = sessionmaker(bind=_engine)
    
    # Создаём таблицы
    Base.metadata.create_all(_engine)
    logger.info(f"База данных инициализирована: {db_path}")


def get_session() -> Session:
    """
    Получить сессию базы данных.
    
    Returns:
        Сессия SQLAlchemy
    """
    if _SessionLocal is None:
        raise RuntimeError("База данных не инициализирована. Вызовите init_db() сначала.")
    return _SessionLocal()

