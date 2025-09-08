import logging
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from llm_providers.base_llm import BaseLLMProvider
from llm_providers.config import llm_settings_manager

class OpenAILLMProvider(BaseLLMProvider):
    """
    Реализация LLM провайдера для OpenAI.
    """
    def __init__(self):
        self._supported_models = ["gpt-3.5-turbo", "gpt-4", "gpt-4o"] # Пример поддерживаемых моделей

    def get_llm_instance(self, model_name: str, temperature: float) -> ChatOpenAI:
        api_key = llm_settings_manager.settings.OPENAI_API_KEY
        if not api_key:
            raise ValueError("OpenAI API ключ не настроен.")
        
        if model_name not in self._supported_models:
            logging.warning(f"Модель {model_name} не поддерживается OpenAILLMProvider. Использую первую доступную: {self._supported_models[0]}")
            model_name = self._supported_models[0]

        return ChatOpenAI(model=model_name, temperature=temperature, api_key=api_key)

    async def generate_text(self, prompt: str, model_name: str, temperature: float) -> str:
        try:
            llm = self.get_llm_instance(model_name, temperature)
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            return response.content
        except Exception as e:
            logging.error(f"Ошибка генерации текста через OpenAI: {e}", exc_info=True)
            return f"Ошибка генерации текста через OpenAI: {e}"

    def get_supported_models(self) -> list[str]:
        return self._supported_models

    async def test_connection(self) -> bool:
        try:
            llm = self.get_llm_instance(self._supported_models[0], 0.1)
            response = await llm.ainvoke([HumanMessage(content="Hello")])
            return response.content is not None and len(response.content) > 0
        except Exception as e:
            logging.error(f"Тест соединения OpenAI провален: {e}", exc_info=True)
            return False
