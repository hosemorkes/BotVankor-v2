"""
ORM-модели, CRUD операции и инициализация базы данных.
"""

import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Text, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
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
    district_coefficient = Column(Float, default=1.0)
    northern_allowance_rate = Column(Float, default=0.0)
    overtime_hours = Column(Float, default=0.0)
    bonus = Column(Float, default=0.0)
    gross = Column(Float, nullable=False)
    gross_with_coefficient = Column(Float, nullable=False)
    northern_allowance = Column(Float, default=0.0)
    overtime_pay = Column(Float, default=0.0)
    total = Column(Float, nullable=False)
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
        
        Raises:
            SQLAlchemyError: При ошибках работы с БД
        """
        try:
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
        except IntegrityError as e:
            session.rollback()
            logger.error(f"Ошибка целостности БД при создании пользователя telegram_id={telegram_id}: {e}")
            raise
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Ошибка БД при работе с пользователем telegram_id={telegram_id}: {e}")
            raise
    
    @staticmethod
    def get_by_telegram_id(session: Session, telegram_id: int) -> Optional[User]:
        """
        Получить пользователя по Telegram ID.
        
        Args:
            session: Сессия БД
            telegram_id: Telegram ID пользователя
        
        Returns:
            Объект User или None если не найден
        
        Raises:
            SQLAlchemyError: При ошибках работы с БД
        """
        try:
            return session.query(User).filter_by(telegram_id=telegram_id).first()
        except SQLAlchemyError as e:
            logger.error(f"Ошибка БД при получении пользователя telegram_id={telegram_id}: {e}")
            raise


class SalaryCRUD:
    """CRUD операции для записей о зарплате."""
    
    @staticmethod
    def create(
        session: Session,
        user_id: int,
        base_salary: float,
        hours_worked: float,
        gross: float,
        gross_with_coefficient: float,
        total: float,
        tax: float,
        net: float,
        district_coefficient: float = 1.0,
        northern_allowance_rate: float = 0.0,
        northern_allowance: float = 0.0,
        overtime_hours: float = 0.0,
        overtime_pay: float = 0.0,
        bonus: float = 0.0
    ) -> SalaryRecord:
        """
        Создать запись о зарплате.
        
        Args:
            session: Сессия БД
            user_id: ID пользователя
            base_salary: Базовая ставка
            hours_worked: Отработанные часы
            gross: Оклад до коэффициентов
            gross_with_coefficient: Оклад с районным коэффициентом
            total: Итого до налогов
            tax: Налог
            net: К выплате
            district_coefficient: Районный коэффициент
            northern_allowance_rate: Процент северной надбавки
            northern_allowance: Сумма северной надбавки
            overtime_hours: Переработанные часы
            overtime_pay: Оплата за переработки
            bonus: Бонус
        
        Returns:
            Объект SalaryRecord
        
        Raises:
            SQLAlchemyError: При ошибках работы с БД
        """
        try:
            record = SalaryRecord(
                user_id=user_id,
                base_salary=base_salary,
                hours_worked=hours_worked,
                district_coefficient=district_coefficient,
                northern_allowance_rate=northern_allowance_rate,
                northern_allowance=northern_allowance,
                overtime_hours=overtime_hours,
                overtime_pay=overtime_pay,
                bonus=bonus,
                gross=gross,
                gross_with_coefficient=gross_with_coefficient,
                total=total,
                tax=tax,
                net=net
            )
            session.add(record)
            session.commit()
            logger.debug(f"Создана запись о зарплате для user_id={user_id}")
            return record
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Ошибка БД при создании записи о зарплате user_id={user_id}: {e}")
            raise
    
    @staticmethod
    def get_user_records(session: Session, user_id: int, limit: int = 10) -> list[SalaryRecord]:
        """
        Получить последние записи пользователя.
        
        Args:
            session: Сессия БД
            user_id: ID пользователя
            limit: Максимальное количество записей
        
        Returns:
            Список записей SalaryRecord
        
        Raises:
            SQLAlchemyError: При ошибках работы с БД
        """
        try:
            return session.query(SalaryRecord).filter_by(user_id=user_id)\
                .order_by(SalaryRecord.created_at.desc()).limit(limit).all()
        except SQLAlchemyError as e:
            logger.error(f"Ошибка БД при получении записей о зарплате user_id={user_id}: {e}")
            raise


class WeatherCRUD:
    """CRUD операции для записей о погоде."""
    
    @staticmethod
    def create(session: Session, user_id: int, city: str, weather_data: str) -> WeatherRecord:
        """
        Создать запись о запросе погоды.
        
        Args:
            session: Сессия БД
            user_id: ID пользователя
            city: Название города
            weather_data: JSON строка с данными о погоде
        
        Returns:
            Объект WeatherRecord
        
        Raises:
            SQLAlchemyError: При ошибках работы с БД
        """
        try:
            record = WeatherRecord(
                user_id=user_id,
                city=city,
                weather_data=weather_data
            )
            session.add(record)
            session.commit()
            logger.debug(f"Создана запись о погоде для user_id={user_id}, city={city}")
            return record
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Ошибка БД при создании записи о погоде user_id={user_id}: {e}")
            raise


# Инициализация базы данных
_engine: Optional[object] = None
_SessionLocal: Optional[sessionmaker] = None


def init_db(db_path: str) -> None:
    """
    Инициализирует базу данных и создаёт таблицы.
    
    Безопасно для повторных вызовов - не пересоздаёт существующие таблицы.
    
    Args:
        db_path: Путь к файлу базы данных
    
    Raises:
        RuntimeError: При ошибках инициализации БД
    """
    global _engine, _SessionLocal
    
    try:
        # Создаём директорию для БД если её нет
        db_path_obj = Path(db_path)
        db_path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        # Создаём движок SQLAlchemy с настройками для надёжности
        # check_same_thread=False нужен для работы в разных потоках
        # pool_pre_ping=True проверяет соединение перед использованием
        _engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True
        )
        
        # Проверяем подключение
        from sqlalchemy import text
        with _engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        _SessionLocal = sessionmaker(bind=_engine)
        
        # Создаём таблицы (безопасно для повторных вызовов)
        Base.metadata.create_all(_engine, checkfirst=True)
        
        # Выполняем миграции для обновления существующих таблиц
        _migrate_salary_records_table()
        
        logger.info(f"База данных инициализирована: {db_path}")
        
        # Проверяем целостность БД
        _check_db_integrity()
        
    except Exception as e:
        logger.error(f"Ошибка инициализации БД {db_path}: {e}")
        raise RuntimeError(f"Не удалось инициализировать БД: {e}") from e


def _migrate_salary_records_table() -> None:
    """
    Миграция таблицы salary_records для добавления новых колонок.
    
    Добавляет колонки, если они отсутствуют:
    - district_coefficient
    - northern_allowance_rate
    - overtime_hours
    - gross_with_coefficient
    - northern_allowance
    - overtime_pay
    - total
    """
    try:
        from sqlalchemy import text, inspect
        
        inspector = inspect(_engine)
        
        # Проверяем, существует ли таблица
        if "salary_records" not in inspector.get_table_names():
            logger.debug("Таблица salary_records не существует, будет создана автоматически")
            return
        
        # Получаем список существующих колонок
        existing_columns = [col["name"] for col in inspector.get_columns("salary_records")]
        
        # Колонки для добавления с их типами и значениями по умолчанию
        columns_to_add = {
            "district_coefficient": ("FLOAT", "1.0"),
            "northern_allowance_rate": ("FLOAT", "0.0"),
            "overtime_hours": ("FLOAT", "0.0"),
            "gross_with_coefficient": ("FLOAT", None),  # Без значения по умолчанию, но nullable
            "northern_allowance": ("FLOAT", "0.0"),
            "overtime_pay": ("FLOAT", "0.0"),
            "total": ("FLOAT", None),  # Без значения по умолчанию, но nullable
        }
        
        with _engine.begin() as conn:
            for column_name, (column_type, default_value) in columns_to_add.items():
                if column_name not in existing_columns:
                    try:
                        # SQLite поддерживает ADD COLUMN с DEFAULT
                        if default_value is not None:
                            # Для колонок с default значением
                            alter_sql = f"ALTER TABLE salary_records ADD COLUMN {column_name} {column_type} DEFAULT {default_value}"
                        else:
                            # Для колонок без default (gross_with_coefficient) - добавляем как nullable
                            alter_sql = f"ALTER TABLE salary_records ADD COLUMN {column_name} {column_type}"
                        
                        conn.execute(text(alter_sql))
                        
                        # Если это gross_with_coefficient или total, заполняем их значениями
                        if column_name == "gross_with_coefficient":
                            update_sql = text("UPDATE salary_records SET gross_with_coefficient = gross WHERE gross_with_coefficient IS NULL")
                            conn.execute(update_sql)
                        elif column_name == "total":
                            # Для total вычисляем: gross + bonus (старая логика) или gross_with_coefficient + northern_allowance + overtime_pay + bonus
                            # Используем более полную формулу, если есть gross_with_coefficient
                            update_sql = text("""
                                UPDATE salary_records 
                                SET total = COALESCE(
                                    gross_with_coefficient + COALESCE(northern_allowance, 0) + COALESCE(overtime_pay, 0) + COALESCE(bonus, 0),
                                    gross + COALESCE(bonus, 0)
                                )
                                WHERE total IS NULL
                            """)
                            conn.execute(update_sql)
                        
                        logger.info(f"Добавлена колонка {column_name} в таблицу salary_records")
                    except Exception as e:
                        logger.warning(f"Не удалось добавить колонку {column_name}: {e}")
                        # Продолжаем с другими колонками даже при ошибке
        
    except Exception as e:
        logger.warning(f"Ошибка при миграции таблицы salary_records: {e}")


def _check_db_integrity() -> None:
    """Проверяет целостность базы данных."""
    try:
        from sqlalchemy import text
        session = get_session()
        # Простая проверка - пытаемся выполнить запрос
        session.execute(text("SELECT 1"))
        session.close()
        logger.debug("Проверка целостности БД пройдена")
    except Exception as e:
        logger.warning(f"Предупреждение при проверке целостности БД: {e}")


def get_session() -> Session:
    """
    Получить сессию базы данных.
    
    Returns:
        Сессия SQLAlchemy
    """
    if _SessionLocal is None:
        raise RuntimeError("База данных не инициализирована. Вызовите init_db() сначала.")
    return _SessionLocal()

