"""
ORM-модели, CRUD операции и инициализация базы данных.
"""

import logging
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

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
    """Модель записи о зарплате (вахтовый метод)."""
    __tablename__ = "salary_records"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, nullable=False, index=True)
    username = Column(String(100))
    
    # Входные параметры
    hourly_rate = Column(Float, nullable=False)  # Часовая ставка
    days_worked = Column(Float, nullable=False)  # Отработано дней
    night_hours = Column(Float, default=0.0)  # Кол-во ночных смен
    travel_days = Column(Float, default=0.0)  # Дни в пути
    holiday_days = Column(Float, default=0.0)  # Кол-во праздников
    idle_days = Column(Float, default=0.0)  # Кол-во дней простоя
    additional_payments = Column(Float, default=0.0)  # Премии и прочие доплаты
    
    # Результаты расчёта
    salary_by_position = Column(Float, nullable=False)  # Оплата по окладу
    shift_method_payment = Column(Float, default=0.0)  # Доплата за вахтовый метод
    monthly_bonus = Column(Float, default=0.0)  # Премия месячная (33%)
    regional_allowance = Column(Float, default=0.0)  # Региональная надбавка
    northern_allowance = Column(Float, default=0.0)  # Северная надбавка
    net = Column(Float, nullable=False)  # ЗП к выплате
    
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
        telegram_id: int,
        username: Optional[str],
        hourly_rate: float,
        days_worked: float,
        night_hours: float = 0.0,
        travel_days: float = 0.0,
        holiday_days: float = 0.0,
        idle_days: float = 0.0,
        additional_payments: float = 0.0,
        salary_by_position: float = 0.0,
        shift_method_payment: float = 0.0,
        monthly_bonus: float = 0.0,
        regional_allowance: float = 0.0,
        northern_allowance: float = 0.0,
        net: float = 0.0
    ) -> SalaryRecord:
        """
        Создать запись о зарплате (вахтовый метод).
        
        Args:
            session: Сессия БД
            telegram_id: Telegram ID пользователя
            username: Username пользователя
            hourly_rate: Часовая ставка
            days_worked: Отработано дней
            night_hours: Кол-во ночных смен
            travel_days: Дни в пути
            holiday_days: Кол-во праздников
            idle_days: Кол-во дней простоя
            additional_payments: Премии и прочие доплаты
            salary_by_position: Оплата по окладу
            shift_method_payment: Доплата за вахтовый метод
            monthly_bonus: Премия месячная (33%)
            regional_allowance: Региональная надбавка
            northern_allowance: Северная надбавка
            net: ЗП к выплате
        
        Returns:
            Объект SalaryRecord
        
        Raises:
            SQLAlchemyError: При ошибках работы с БД
        """
        try:
            record = SalaryRecord(
                telegram_id=telegram_id,
                username=username,
                hourly_rate=hourly_rate,
                days_worked=days_worked,
                night_hours=night_hours,
                travel_days=travel_days,
                holiday_days=holiday_days,
                idle_days=idle_days,
                additional_payments=additional_payments,
                salary_by_position=salary_by_position,
                shift_method_payment=shift_method_payment,
                monthly_bonus=monthly_bonus,
                regional_allowance=regional_allowance,
                northern_allowance=northern_allowance,
                net=net
            )
            session.add(record)
            session.commit()
            logger.debug(f"Создана запись о зарплате для telegram_id={telegram_id}")
            return record
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Ошибка БД при создании записи о зарплате telegram_id={telegram_id}: {e}")
            raise
    
    @staticmethod
    def get_user_records(session: Session, telegram_id: int, limit: int = 10) -> list[SalaryRecord]:
        """
        Получить последние записи пользователя.
        
        Args:
            session: Сессия БД
            telegram_id: Telegram ID пользователя
            limit: Максимальное количество записей
        
        Returns:
            Список записей SalaryRecord
        
        Raises:
            SQLAlchemyError: При ошибках работы с БД
        """
        try:
            return session.query(SalaryRecord).filter_by(telegram_id=telegram_id)\
                .order_by(SalaryRecord.created_at.desc()).limit(limit).all()
        except SQLAlchemyError as e:
            logger.error(f"Ошибка БД при получении записей о зарплате telegram_id={telegram_id}: {e}")
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
    Миграция таблицы salary_records - пересоздание с новой структурой.
    
    Удаляет старую таблицу и создаёт новую с полями:
    - telegram_id, username
    - hourly_rate, days_worked
    - night_hours, travel_days, holiday_days, idle_days, additional_payments
    - salary_by_position, shift_method_payment, monthly_bonus
    - regional_allowance, northern_allowance, net
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
        
        # Проверяем, нужна ли миграция (если структура уже правильная)
        required_columns = {
            "telegram_id", "username", "hourly_rate", "days_worked",
            "night_hours", "travel_days", "holiday_days", "idle_days", "additional_payments",
            "salary_by_position", "shift_method_payment", "monthly_bonus",
            "regional_allowance", "northern_allowance", "net"
        }
        
        # Если структура уже правильная, не делаем миграцию
        if required_columns.issubset(set(existing_columns)):
            logger.debug("Таблица salary_records уже имеет правильную структуру")
            return
        
        logger.info("Начинаем миграцию таблицы salary_records - пересоздание с новой структурой")
        
        with _engine.begin() as conn:
            # Создаём временную таблицу с новой структурой
            conn.execute(text("""
                CREATE TABLE salary_records_new (
                    id INTEGER NOT NULL PRIMARY KEY,
                    telegram_id INTEGER NOT NULL,
                    username VARCHAR(100),
                    hourly_rate FLOAT NOT NULL,
                    days_worked FLOAT NOT NULL,
                    night_hours FLOAT DEFAULT 0.0,
                    travel_days FLOAT DEFAULT 0.0,
                    holiday_days FLOAT DEFAULT 0.0,
                    idle_days FLOAT DEFAULT 0.0,
                    additional_payments FLOAT DEFAULT 0.0,
                    salary_by_position FLOAT NOT NULL,
                    shift_method_payment FLOAT DEFAULT 0.0,
                    monthly_bonus FLOAT DEFAULT 0.0,
                    regional_allowance FLOAT DEFAULT 0.0,
                    northern_allowance FLOAT DEFAULT 0.0,
                    net FLOAT NOT NULL,
                    created_at DATETIME
                )
            """))
            
            # Удаляем старую таблицу
            conn.execute(text("DROP TABLE salary_records"))
            
            # Переименовываем новую таблицу
            conn.execute(text("ALTER TABLE salary_records_new RENAME TO salary_records"))
            
            # Создаём индекс
            try:
                conn.execute(text("CREATE INDEX ix_salary_records_telegram_id ON salary_records (telegram_id)"))
            except Exception:
                pass  # Индекс может уже существовать
            
            logger.info("Таблица salary_records успешно пересоздана с новой структурой")
        
    except Exception as e:
        logger.error(f"Ошибка при миграции таблицы salary_records: {e}")
        raise


def _check_db_integrity() -> None:
    """Проверяет целостность базы данных."""
    try:
        from sqlalchemy import text
        with db_session() as session:
            # Простая проверка - пытаемся выполнить запрос
            session.execute(text("SELECT 1"))
        logger.debug("Проверка целостности БД пройдена")
    except Exception as e:
        logger.warning(f"Предупреждение при проверке целостности БД: {e}")


def get_session() -> Session:
    """
    Получить сессию базы данных.
    
    ВНИМАНИЕ: Используйте db_session() контекстный менеджер вместо прямого вызова
    для гарантированного закрытия сессии.
    
    Returns:
        Сессия SQLAlchemy
    """
    if _SessionLocal is None:
        raise RuntimeError("База данных не инициализирована. Вызовите init_db() сначала.")
    return _SessionLocal()


@contextmanager
def db_session():
    """
    Контекстный менеджер для безопасной работы с сессией БД.
    
    Гарантирует закрытие сессии даже при возникновении исключений.
    
    Usage:
        with db_session() as session:
            user = UserCRUD.get_by_telegram_id(session, telegram_id=123)
            # Сессия автоматически закроется при выходе из блока
    
    Yields:
        Session: Сессия SQLAlchemy
    
    Raises:
        RuntimeError: Если БД не инициализирована
    """
    if _SessionLocal is None:
        raise RuntimeError("База данных не инициализирована. Вызовите init_db() сначала.")
    
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

