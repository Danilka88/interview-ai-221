from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class STTSettings(BaseSettings):
    # Настройки провайдера STT
    STT_PROVIDER: str = "vosk" # 'vosk', 'google_cloud', 'yandex_speechkit', 'azure_cognitive_services', 'openai_whisper'

    # Ключи API для облачных сервисов
    GOOGLE_CLOUD_SPEECH_API_KEY: Optional[str] = None
    YANDEX_SPEECHKIT_API_KEY: Optional[str] = None
    AZURE_COGNITIVE_SERVICES_SPEECH_KEY: Optional[str] = None
    AZURE_COGNITIVE_SERVICES_SPEECH_REGION: Optional[str] = None
    OPENAI_WHISPER_API_KEY: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra='ignore')

stt_settings = STTSettings()
