from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class AudioProcessingSettings(BaseSettings):
    # Настройки шумоподавления
    AUDIO_PROCESSING_ENABLED: bool = False
    NOISE_REDUCTION_RATE: float = 0.8 # Степень подавления шума (0.0 - 1.0)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra='ignore')

# Создаем синглтон для настроек, чтобы они были доступны по всему приложению
class SettingsManager:
    _instance = None
    _settings: AudioProcessingSettings

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SettingsManager, cls).__new__(cls)
            cls._instance._settings = AudioProcessingSettings()
        return cls._instance

    @property
    def settings(self) -> AudioProcessingSettings:
        return self._settings

    def update_settings(self, new_settings_data: dict):
        for key, value in new_settings_data.items():
            if hasattr(self._settings, key):
                setattr(self._settings, key, value)
            else:
                print(f"Warning: Attempted to update unknown audio processing setting: {key}")

audio_processing_settings_manager = SettingsManager()
