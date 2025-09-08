import logging
from typing import Dict, Type, Any

from llm_providers.base_llm import BaseLLMProvider
from llm_providers.ollama_llm import OllamaLLMProvider
from llm_providers.openai_llm import OpenAILLMProvider
from llm_providers.yandex_llm import YandexLLMProvider
from llm_providers.sber_llm import SberLLMProvider
from llm_providers.config import llm_settings_manager

# Словарь доступных провайдеров LLM
LLM_PROVIDERS: Dict[str, BaseLLMProvider] = {
    "ollama": OllamaLLMProvider(),
    "openai": OpenAILLMProvider(),
    "yandexgpt": YandexLLMProvider(),
    "sber_gigachat": SberLLMProvider(),
}

def get_current_llm_provider() -> BaseLLMProvider:
    """
    Возвращает текущий активный LLM провайдер на основе настроек.
    """
    provider_name = llm_settings_manager.settings.LLM_PROVIDER
    provider = LLM_PROVIDERS.get(provider_name)
    if not provider:
        logging.error(f"Неизвестный LLM провайдер в настройках: {provider_name}. Использую Ollama по умолчанию.")
        return LLM_PROVIDERS["ollama"]
    return provider


def get_llm_instance(model_name: str, temperature: float) -> Any:
    """
    Возвращает экземпляр LLM для использования в цепочках LangChain.
    """
    provider = get_current_llm_provider()
    return provider.get_llm_instance(model_name, temperature)


async def generate_text_with_current_llm(prompt: str, model_name: str, temperature: float) -> str:
    """
    Генерирует текст с использованием текущего выбранного LLM провайдера.
    """
    provider = get_current_llm_provider()
    return await provider.generate_text(prompt, model_name, temperature)
