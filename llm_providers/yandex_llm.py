import logging
from typing import Any

# from langchain_community.chat_models import ChatYandexGPT # Заглушка, если нет прямой интеграции
from langchain_core.messages import HumanMessage

from llm_providers.base_llm import BaseLLMProvider
from llm_providers.config import llm_settings_manager

# Заглушка для ChatYandexGPT, если библиотека не установлена или нет прямой интеграции
class ChatYandexGPT:
    def __init__(self, model_name: str, temperature: float, api_key: str):
        logging.warning("Используется заглушка ChatYandexGPT. Установите 'langchain-community' с поддержкой YandexGPT для полноценной работы.")
        self.model_name = model_name
        self.temperature = temperature
        self.api_key = api_key

    async def ainvoke(self, messages: list) -> Any:
        # Здесь должна быть реальная логика вызова YandexGPT API
        # Для заглушки просто возвращаем имитацию ответа
        if not self.api_key:
            raise ValueError("YandexGPT API ключ не настроен.")
        logging.info(f"Заглушка YandexGPT: Получен запрос: {messages[0].content}")
        await asyncio.sleep(0.1) # Имитация задержки
        return HumanMessage(content=f"Заглушка ответа YandexGPT на: {messages[0].content[:50]}...")


class YandexLLMProvider(BaseLLMProvider):
    """
    Реализация LLM провайдера для YandexGPT.
    """
    def __init__(self):
        self._supported_models = ["yandexgpt-lite", "yandexgpt-pro"] # Пример поддерживаемых моделей

    def get_llm_instance(self, model_name: str, temperature: float) -> ChatYandexGPT:
        api_key = llm_settings_manager.settings.YANDEX_GPT_API_KEY
        if not api_key:
            raise ValueError("YandexGPT API ключ не настроен.")
        
        if model_name not in self._supported_models:
            logging.warning(f"Модель {model_name} не поддерживается YandexLLMProvider. Использую первую доступную: {self._supported_models[0]}")
            model_name = self._supported_models[0]

        return ChatYandexGPT(model_name=model_name, temperature=temperature, api_key=api_key)

    async def generate_text(self, prompt: str, model_name: str, temperature: float) -> str:
        try:
            llm = self.get_llm_instance(model_name, temperature)
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            return response.content
        except Exception as e:
            logging.error(f"Ошибка генерации текста через YandexGPT: {e}", exc_info=True)
            return f"Ошибка генерации текста через YandexGPT: {e}"

    def get_supported_models(self) -> list[str]:
        return self._supported_models

    async def test_connection(self) -> bool:
        try:
            llm = self.get_llm_instance(self._supported_models[0], 0.1)
            response = await llm.ainvoke([HumanMessage(content="Привет")])
            return response.content is not None and len(response.content) > 0
        except Exception as e:
            logging.error(f"Тест соединения YandexGPT провален: {e}", exc_info=True)
            return False
