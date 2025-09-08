"""
Главный файл для запуска FastAPI приложения AI Interviewer.

Этот файл собирает все маршрутизаторы, настраивает CORS и определяет
обработчики событий жизненного цикла приложения (startup, shutdown).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text # <--- Импортируем text

# Импорт модулей для инициализации БД
from core.database import engine, Base
from core import schemas # Убедимся, что модуль со схемами импортирован

# Импорт маршрутизаторов
from api import ranking, interview, general, dashboard, webhook, api_v1, stt_settings, stt_interview # Импорт существующих роутеров и нового api_v1
from audio_processing.api import router as audio_processing_router # Импорт роутера для обработки аудио
from llm_providers.api import router as llm_providers_router # Импорт роутера для LLM провайдеров

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Контекстный менеджер для управления жизненным циклом приложения."""
    logging.info("Приложение запускается...")
    # Создаем таблицы в базе данных
    async with engine.begin() as conn:
        # Включаем поддержку внешних ключей для SQLite
        await conn.run_sync(lambda sync_conn: sync_conn.execute(text("PRAGMA foreign_keys=ON")))
        # Создаем все таблицы, определенные в Base
        await conn.run_sync(Base.metadata.create_all)
    logging.info("База данных и таблицы успешно инициализированы.")
    yield
    logging.info("Приложение останавливается...")


# Создание экземпляра FastAPI с менеджером жизненного цикла
app = FastAPI(lifespan=lifespan)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Разрешить все источники
    allow_credentials=True,
    allow_methods=["*"],  # Разрешить все методы
    allow_headers=["*"],  # Разрешить все заголовки
)

# Подключение маршрутизаторов
app.include_router(general.router)
app.include_router(interview.router)
app.include_router(ranking.router)
app.include_router(webhook.router)
app.include_router(api_v1.router)
app.include_router(dashboard.router)
app.include_router(stt_settings.router) # New router for STT settings
app.include_router(stt_interview.router) # New router for STT-enabled interview
app.include_router(audio_processing_router) # New router for audio processing
app.include_router(llm_providers_router) # New router for LLM providers

# Подключение статических файлов
app.mount("/static", StaticFiles(directory="static"), name="static")