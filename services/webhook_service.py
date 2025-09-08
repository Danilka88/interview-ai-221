"""
Сервис для обработки логики, связанной с Webhook API.

Включает в себя функции для выполнения фоновых задач и безопасной отправки
результатов на указанные webhook URL.
"""

import logging
import httpx
import hmac
import hashlib
import json

from core.config import settings
from core.models import WebhookRankRequest, WebhookAnalysisRequest
from services.ai_services import score_and_sort_resumes, analyst_chain
from prompts.interview_prompts import DEFAULT_JOB_DESCRIPTION

async def send_webhook(
    url: str,
    data: dict,
    secret: str
) -> bool:
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
        logging.error(f"[WEBHOOK] КРИТИЧЕСКАЯ ОШИБКА: Не удалось отправить вебхук на {url}. Причина: {e}", exc_info=True)
        return False

async def process_ranking_request(request: WebhookRankRequest):
    """Фоновая задача для выполнения ранжирования резюме."""
    logging.info(f"[WEBHOOK] Запуск задачи ранжирования для {request.webhook_url}")
    try:
        # Конвертируем Pydantic модели в словари для передачи в сервис
        resumes_data = [r.model_dump() for r in request.resumes]
        
        # Вызываем централизованный сервис
        sorted_results = await score_and_sort_resumes(request.vacancy_text, resumes_data)
        
        final_payload = {
            "status": "completed",
            "request_data": request.model_dump(exclude={"webhook_url"}), # Возвращаем исходные данные для контекста
            "result": {"ranking": sorted_results}
        }
        await send_webhook(url=str(request.webhook_url), data=final_payload, secret=settings.WEBHOOK_SECRET_TOKEN)

    except Exception as e:
        logging.error(f"[WEBHOOK] Сбой задачи ранжирования для {request.webhook_url}. Причина: {e}", exc_info=True)
        error_payload = {
            "status": "failed",
            "error": str(e)
        }
        await send_webhook(url=str(request.webhook_url), data=error_payload, secret=settings.WEBHOOK_SECRET_TOKEN)

async def process_analysis_request(request: WebhookAnalysisRequest):
    """Фоновая задача для выполнения анализа интервью."""
    logging.info(f"[WEBHOOK] Запуск задачи анализа интервью для {request.webhook_url}")
    try:
        history_str = "\n".join([f"{log.sender}: {log.text}" for log in request.conversation_history])
        
        analysis_str = await analyst_chain.apredict(
            vacancy_text=(request.vacancy_text or DEFAULT_JOB_DESCRIPTION),
            resume_text=(request.resume_text or "Резюме не предоставлено."),
            dialogue_log=history_str
        )
        
        analysis_json = json.loads(analysis_str)

        final_payload = {
            "status": "completed",
            "request_data": request.model_dump(exclude={"webhook_url"}),
            "result": analysis_json
        }
        await send_webhook(url=str(request.webhook_url), data=final_payload, secret=settings.WEBHOOK_SECRET_TOKEN)

    except Exception as e:
        logging.error(f"[WEBHOOK] Сбой задачи анализа для {request.webhook_url}. Причина: {e}", exc_info=True)
        error_payload = {
            "status": "failed",
            "error": str(e)
        }
        await send_webhook(url=str(request.webhook_url), data=error_payload, secret=settings.WEBHOOK_SECRET_TOKEN)
