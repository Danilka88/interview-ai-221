import logging
import os
import json
from typing import Any, Optional

from vosk import Model, KaldiRecognizer

from services.stt_providers.base_stt import BaseSTTProvider
from services.voice_processing import get_vosk_model, SAMPLE_RATE # Re-use existing Vosk model loading

class VoskSTTProvider(BaseSTTProvider):
    """
    Реализация STT провайдера для Vosk.
    """
    def __init__(self):
        self._supported_languages = ["ru", "en-us", "de", "fr", "es", "pt", "zh", "vn", "it", "nl", "ca", "ar", "fa", "tl-ph", "uk", "kz", "tr", "hi"]

    def get_recognizer(self, language_code: str = "ru") -> KaldiRecognizer:
        """
        Возвращает объект KaldiRecognizer для Vosk.
        """
        vosk_model = get_vosk_model(language_code)
        if not vosk_model:
            raise ValueError(f"Модель Vosk для языка '{language_code}' не найдена или не загружена.")
        return KaldiRecognizer(vosk_model, SAMPLE_RATE)

    async def recognize_audio_chunk(self, recognizer: KaldiRecognizer, audio_chunk: bytes) -> Optional[str]:
        """
        Обрабатывает фрагмент аудио с помощью Vosk и возвращает частичный результат.
        """
        if recognizer.AcceptWaveform(audio_chunk):
            # Full result is available, but we only want partial here
            return None
        else:
            partial_result = json.loads(recognizer.PartialResult())
            return partial_result.get('partial', '')

    async def get_final_result(self, recognizer: KaldiRecognizer) -> Optional[str]:
        """
        Возвращает окончательный распознанный текст от Vosk.
        """
        final_result_json = recognizer.FinalResult()
        return json.loads(final_result_json).get('text', '')

    def get_supported_languages(self) -> list[str]:
        """
        Возвращает список поддерживаемых языков для Vosk.
        """
        return self._supported_languages
