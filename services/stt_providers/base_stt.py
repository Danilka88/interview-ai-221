from abc import ABC, abstractmethod
from typing import Any, Optional

class BaseSTTProvider(ABC):
    """
    Абстрактный базовый класс для всех провайдеров Speech-to-Text.
    """

    @abstractmethod
    def get_recognizer(self, language_code: str = "ru") -> Any:
        """
        Возвращает объект распознавателя, специфичный для провайдера.
        Это может быть объект Vosk KaldiRecognizer, клиент Google Speech, и т.д.
        """
        pass

    @abstractmethod
    async def recognize_audio_chunk(self, recognizer: Any, audio_chunk: bytes) -> Optional[str]:
        """
        Обрабатывает фрагмент аудио и возвращает распознанный текст (частичный или полный).
        """
        pass

    @abstractmethod
    async def get_final_result(self, recognizer: Any) -> Optional[str]:
        """
        Возвращает окончательный распознанный текст после завершения потока аудио.
        """
        pass

    @abstractmethod
    def get_supported_languages(self) -> list[str]:
        """
        Возвращает список поддерживаемых языков для данного провайдера.
        """
        pass
