import logging
from typing import Any

from langchain_community.chat_models import ChatOllama
from langchain_core.messages import HumanMessage

from llm_providers.base_llm import BaseLLMProvider

class OllamaLLMProvider(BaseLLMProvider):
    """
    Реализация LLM провайдера для Ollama.
    """
    def __init__(self):
        self._supported_models = ["gemma3:4b", "qwen2.5-coder:3b"] # Пример поддерживаемых моделей

    def get_llm_instance(self, model_name: str, temperature: float) -> ChatOllama:
        if model_name not in self._supported_models:
            logging.warning(f"Модель {model_name} не поддерживается OllamaLLMProvider. Использую первую доступную: {self._supported_models[0]}")
            model_name = self._supported_models[0]
        return ChatOllama(model=model_name, temperature=temperature)

    async def generate_text(self, prompt: str, model_name: str, temperature: float) -> str:
        llm = self.get_llm_instance(model_name, temperature)
        try:
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            return response.content
        except Exception as e:
            logging.error(f"Ошибка генерации текста через Ollama: {e}", exc_info=True)
            return f"Ошибка генерации текста через Ollama: {e}"

    def get_supported_models(self) -> list[str]:
        return self._supported_models

    async def test_connection(self) -> bool:
        try:
            # Попытка получить экземпляр LLM и сделать простой вызов
            llm = self.get_llm_instance(self._supported_models[0], 0.1)
            response = await llm.ainvoke([HumanMessage(content="Hello")])
            return response.content is not None and len(response.content) > 0
        except Exception as e:
            logging.error(f"Тест соединения Ollama провален: {e}", exc_info=True)
            return False
