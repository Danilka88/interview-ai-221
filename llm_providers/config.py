from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, Dict, Any

class LLMSettings(BaseSettings):
    # Настройки провайдера LLM
    LLM_PROVIDER: str = "ollama" # 'ollama', 'openai', 'yandexgpt', 'sber_gigachat'

    # Ключи API для облачных сервисов
    OPENAI_API_KEY: Optional[str] = None
    YANDEX_GPT_API_KEY: Optional[str] = None
    SBER_GIGACHAT_API_KEY: Optional[str] = None

    # Модели по умолчанию для разных ролей
    DEFAULT_OLLAMA_MODEL: str = "gemma3:4b"
    DEFAULT_OPENAI_MODEL: str = "gpt-3.5-turbo"
    DEFAULT_YANDEX_GPT_MODEL: str = "yandexgpt-lite"
    DEFAULT_SBER_GIGACHAT_MODEL: str = "GigaChat"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra='ignore')

# Создаем синглтон для настроек, чтобы они были доступны по всему приложению
class LLMSettingsManager:
    _instance = None
    _settings: LLMSettings

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LLMSettingsManager, cls).__new__(cls)
            cls._instance._settings = LLMSettings()
        return cls._instance

    @property
    def settings(self) -> LLMSettings:
        return self._settings

    def update_settings(self, new_settings_data: Dict[str, Any]):
        for key, value in new_settings_data.items():
            if hasattr(self._settings, key):
                setattr(self._settings, key, value)
            else:
                print(f"Warning: Attempted to update unknown LLM setting: {key}")

llm_settings_manager = LLMSettingsManager()
