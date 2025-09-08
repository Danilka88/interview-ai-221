from abc import ABC, abstractmethod
from typing import Any, Optional

class BaseLLMProvider(ABC):
    """
    Абстрактный базовый класс для всех провайдеров LLM.
    """

    @abstractmethod
    def get_llm_instance(self, model_name: str, temperature: float) -> Any:
        """
        Возвращает экземпляр LLM (например, ChatOllama, ChatOpenAI).
        """
        pass

    @abstractmethod
    async def generate_text(self, prompt: str, model_name: str, temperature: float) -> str:
        """
        Генерирует текст с использованием LLM.
        """
        pass

    @abstractmethod
    def get_supported_models(self) -> list[str]:
        """
        Возвращает список поддерживаемых моделей для данного провайдера.
        """
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """
        Тестирует соединение с провайдером LLM.
        """
        pass
