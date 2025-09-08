import logging
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks, Header, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, HttpUrl

from llm_providers.config import llm_settings_manager
from llm_providers.llm_selector import get_current_llm_provider, generate_text_with_current_llm

# Для вебхуков
import httpx
import hmac
import hashlib
import json

router = APIRouter()

# Pydantic model for incoming LLM settings
class LLMConfigUpdate(BaseModel):
    LLM_PROVIDER: str
    OPENAI_API_KEY: Optional[str] = None
    YANDEX_GPT_API_KEY: Optional[str] = None
    SBER_GIGACHAT_API_KEY: Optional[str] = None

# Pydantic model for text generation request
class GenerateTextRequest(BaseModel):
    prompt: str
    model_name: Optional[str] = None # Allow overriding default model
    temperature: float = 0.7 # Default temperature

# Pydantic model for webhook text generation request
class WebhookGenerateTextRequest(BaseModel):
    webhook_url: HttpUrl
    prompt: str
    model_name: Optional[str] = None
    temperature: float = 0.7

# --- HTML Page Endpoint ---
@router.get("/llm-providers/settings", response_class=HTMLResponse)
async def get_llm_providers_settings_page():
    """Serves the LLM providers settings HTML page."""
    return Path("llm_providers/settings.html").read_text(encoding="utf-8")

# --- API Endpoints for Settings ---
@router.get("/api/v1/llm-providers/config")
async def get_llm_providers_config():
    """Returns the current LLM providers configuration."""
    return llm_settings_manager.settings.model_dump()

@router.post("/api/v1/llm-providers/config")
async def update_llm_providers_config(config_update: LLMConfigUpdate):
    """Updates the LLM providers configuration at runtime."""
    try:
        llm_settings_manager.update_settings(config_update.model_dump())
        logging.info(f"LLM providers settings updated at runtime: {config_update.model_dump()}")
        return {"message": "LLM providers settings updated successfully."}
    except Exception as e:
        logging.error(f"Error updating LLM providers settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update LLM providers settings: {e}")

@router.post("/api/v1/llm-providers/test")
async def test_llm_providers_config(test_request: LLMConfigUpdate):
    """Tests the provided LLM providers configuration."""
    try:
        # Temporarily apply settings for testing without persisting
        original_llm_settings = llm_settings_manager.settings.model_copy()
        llm_settings_manager.update_settings(test_request.model_dump())

        provider = get_current_llm_provider()
        success = await provider.test_connection()
        
        if success:
            return {"success": True, "message": f"LLM провайдер '{test_request.LLM_PROVIDER}' успешно настроен и готов к работе."}
        else:
            raise Exception("Провайдер не прошел внутренний тест соединения.")

    except Exception as e:
        logging.error(f"LLM test failed for {test_request.LLM_PROVIDER}: {e}", exc_info=True)
        return {"success": False, "message": f"Ошибка тестирования LLM провайдера '{test_request.LLM_PROVIDER}': {e}"}
    finally:
        # Revert to original settings after testing
        llm_settings_manager.update_settings(original_llm_settings.model_dump())

# --- API Endpoint for Text Generation ---
@router.post("/api/v1/llm-providers/generate")
async def generate_text_api(request: GenerateTextRequest):
    """
    Генерирует текст с использованием текущего выбранного LLM провайдера.
    """
    try:
        generated_text = await generate_text_with_current_llm(
            prompt=request.prompt,
            model_name=request.model_name,
            temperature=request.temperature
        )
        return {"generated_text": generated_text}
    except Exception as e:
        logging.error(f"Ошибка при генерации текста через API: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка генерации текста: {e}")

# --- Webhook Endpoint for Text Generation ---
async def send_webhook(url: str, data: dict, secret: str) -> bool:
    """
    Асинхронно отправляет данные на указанный URL с подписью HMAC-SHA256.
    """
    try:
        payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
        signature = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
        
        headers = {
            'Content-Type': 'application/json',
            'X-Webhook-Signature-256': f"sha256={signature}"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, content=payload, headers=headers, timeout=30.0)
            response.raise_for_status()
            
        logging.info(f"Вебхук успешно отправлен на {url}. Статус: {response.status_code}")
        return True
    except Exception as e:
        logging.error(f"[LLM Webhook] КРИТИЧЕСКАЯ ОШИБКА: Не удалось отправить вебхук на {url}. Причина: {e}", exc_info=True)
        return False

async def process_webhook_generate_request(request: WebhookGenerateTextRequest):
    """
    Фоновая задача для генерации текста через вебхук.
    """
    try:
        generated_text = await generate_text_with_current_llm(
            prompt=request.prompt,
            model_name=request.model_name,
            temperature=request.temperature
        )
        final_payload = {"status": "completed", "generated_text": generated_text}
        await send_webhook(url=str(request.webhook_url), data=final_payload, secret="llm-webhook-secret") # TODO: Секрет должен быть из настроек
    except Exception as e:
        logging.error(f"[LLM Webhook] Сбой задачи генерации текста: {e}", exc_info=True)
        error_payload = {"status": "failed", "error": str(e)}
        await send_webhook(url=str(request.webhook_url), data=error_payload, secret="llm-webhook-secret") # TODO: Секрет должен быть из настроек

@router.post("/api/v1/llm-providers/webhook/generate")
async def webhook_generate_text(request: WebhookGenerateTextRequest, background_tasks: BackgroundTasks):
    """
    Принимает запрос на генерацию текста через вебхук и запускает фоновую задачу.
    """
    logging.info(f"[LLM Webhook] Принят запрос на генерацию текста для {request.webhook_url}")
    background_tasks.add_task(process_webhook_generate_request, request)
    return {"message": "Text generation task accepted and is being processed in the background."}
