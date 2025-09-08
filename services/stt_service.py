import logging
from typing import Any, Optional

from core.settings_manager import settings_manager
from services.stt_providers.base_stt import BaseSTTProvider
from services.stt_providers.vosk_stt import VoskSTTProvider
from services.stt_providers.google_cloud_stt import GoogleCloudSTTProvider
from services.stt_providers.yandex_speechkit_stt import YandexSpeechKitSTTProvider

# Map provider names to their implementations
STT_PROVIDERS = {
    "vosk": VoskSTTProvider(),
    "google_cloud": GoogleCloudSTTProvider(),
    "yandex_speechkit": YandexSpeechKitSTTProvider(),
    # Add other providers here as they are implemented
}

def get_current_stt_provider() -> BaseSTTProvider:
    """
    Возвращает текущий активный STT провайдер на основе настроек.
    """
    provider_name = settings_manager.stt_settings.STT_PROVIDER
    provider = STT_PROVIDERS.get(provider_name)
    if not provider:
        logging.error(f"Неизвестный STT провайдер в настройках: {provider_name}. Использую Vosk по умолчанию.")
        return STT_PROVIDERS["vosk"]
    return provider

async def recognize_audio_stream(websocket: Any, stt_provider: BaseSTTProvider, language_code: str):
    """
    Обрабатывает потоковое аудио с использованием выбранного STT провайдера.
    """
    recognizer = None
    try:
        recognizer = stt_provider.get_recognizer(language_code)
        
        while True:
            data = await websocket.receive_bytes()

            if not data: # End of stream
                final_text = await stt_provider.get_final_result(recognizer)
                if final_text:
                    await websocket.send_json({"type": "text", "sender": "User", "data": final_text})
                break # Exit loop after final result
            
            partial_text = await stt_provider.recognize_audio_chunk(recognizer, data)
            if partial_text:
                await websocket.send_json({"type": "partial_text", "data": partial_text})

    except Exception as e:
        logging.error(f"Ошибка в потоковом распознавании речи: {e}", exc_info=True)
        await websocket.send_json({"type": "error", "message": f"Ошибка распознавания речи: {e}"})
    finally:
        # Clean up recognizer if necessary (e.g., close connections)
        pass # For Vosk, no explicit cleanup needed here
