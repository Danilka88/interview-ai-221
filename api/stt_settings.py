import logging
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core.settings_manager import settings_manager
from services.stt_service import get_current_stt_provider, STT_PROVIDERS

router = APIRouter()

# Pydantic model for incoming STT settings
class STTConfigUpdate(BaseModel):
    STT_PROVIDER: str
    GOOGLE_CLOUD_SPEECH_API_KEY: Optional[str] = None
    YANDEX_SPEECHKIT_API_KEY: Optional[str] = None
    # Add fields for other providers here

# Pydantic model for testing STT settings
class STTTestRequest(BaseModel):
    STT_PROVIDER: str
    GOOGLE_CLOUD_SPEECH_API_KEY: Optional[str] = None
    YANDEX_SPEECHKIT_API_KEY: Optional[str] = None
    # Add fields for other providers here

@router.get("/stt-settings", response_class=HTMLResponse)
async def get_stt_settings_page():
    """Serves the STT settings HTML page."""
    return Path("stt_settings.html").read_text(encoding="utf-8")

@router.get("/api/v1/stt-config")
async def get_stt_config():
    """Returns the current STT configuration."""
    return settings_manager.stt_settings.model_dump()

@router.post("/api/v1/stt-config")
async def update_stt_config(config_update: STTConfigUpdate):
    """Updates the STT configuration at runtime."""
    try:
        settings_manager.update_stt_settings(config_update.model_dump())
        logging.info(f"STT settings updated at runtime: {config_update.STT_PROVIDER}")
        return {"message": "STT settings updated successfully."}
    except Exception as e:
        logging.error(f"Error updating STT settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update STT settings: {e}")

@router.post("/api/v1/stt-test")
async def test_stt_config(test_request: STTTestRequest):
    """Tests the provided STT configuration."""
    try:
        # Temporarily apply settings for testing without persisting
        original_stt_settings = settings_manager.stt_settings.model_copy()
        settings_manager.update_stt_settings(test_request.model_dump())

        provider_name = test_request.STT_PROVIDER
        provider_instance = STT_PROVIDERS.get(provider_name)

        if not provider_instance:
            raise ValueError(f"Неизвестный STT провайдер: {provider_name}")

        # Attempt to get a recognizer to test configuration
        # For Vosk, this checks if the model is loaded
        # For cloud providers, this might check API key validity (if implemented in get_recognizer)
        recognizer = provider_instance.get_recognizer("ru") # Use Russian for testing
        
        # Perform a dummy recognition if possible
        if hasattr(provider_instance, 'test_connection'): # Add a test_connection method to providers
            test_result = await provider_instance.test_connection()
            if not test_result:
                raise Exception("Провайдер не прошел внутренний тест соединения.")

        return {"success": True, "message": f"STT провайдер '{provider_name}' успешно настроен и готов к работе."}

    except Exception as e:
        logging.error(f"STT test failed for {test_request.STT_PROVIDER}: {e}", exc_info=True)
        return {"success": False, "message": f"Ошибка тестирования STT провайдера '{test_request.STT_PROVIDER}': {e}"}
    finally:
        # Revert to original settings after testing
        settings_manager.update_stt_settings(original_stt_settings.model_dump())
