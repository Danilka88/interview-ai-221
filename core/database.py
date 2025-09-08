"""
Модуль для настройки подключения к базе данных и управления сессиями.
"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

# URL для подключения к нашей SQLite базе данных. Файл будет создан в корне проекта.
SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./interview_ai.db"

# Создаем асинхронный "движок" SQLAlchemy
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False} # Обязательно для SQLite
)

# Создаем фабрику сессий для асинхронной работы
AsyncSessionFactory = async_sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine
)

# Базовый класс для всех наших моделей данных (таблиц)
Base = declarative_base()

# Зависимость для FastAPI: предоставляет сессию базы данных в эндпоинты
async def get_db() -> AsyncSession:
    """Создает и отдает асинхронную сессию БД, закрывая ее после использования."""
    async with AsyncSessionFactory() as session:
        yield session
