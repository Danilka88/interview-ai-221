"""
Модуль для управления конфигурацией приложения.

Использует pydantic-settings для чтения настроек из переменных окружения
(включая файл .env). Это позволяет гибко настраивать приложение
без изменения исходного кода.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Настройки моделей LLM
    LLM_INTERVIEWER_MODEL: str = "gemma3:4b"
    LLM_CANDIDATE_MODEL: str = "qwen2.5-coder:3b"
    LLM_QUESTION_GEN_MODEL: str = "gemma3:4b"
    LLM_ANALYST_MODEL: str = "gemma3:4b"

    # Настройки моделей обработки голоса
    VOSK_MODEL_PATH: str = "vosk-model-ru"
    SILERO_MODEL_PATH: str = "v3_1_ru.pt"

    # Секретный токен для аутентификации вебхуков
    WEBHOOK_SECRET_TOKEN: str = "change-me-in-dot-env-file"

    # Конфигурация pydantic-settings
    # Указывает, что нужно читать переменные из файла .env
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8')

# Создаем единый экземпляр настроек, который будет использоваться во всем приложении
settings = Settings()
