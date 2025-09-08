"""
API-маршрутизатор для обработки входящих вебхук-запросов от внешних систем.

Обеспечивает асинхронный запуск задач и аутентификацию по токену.
"""

from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from typing import Annotated

from core.config import settings
from core.models import WebhookRankRequest, WebhookAnalysisRequest
from services.webhook_service import process_ranking_request, process_analysis_request

# --- Зависимость для проверки безопасности ---

async def verify_token(x_webhook_token: Annotated[str, Header()]) -> None:
    """
    Проверяет, совпадает ли токен из заголовка с токеном из настроек.
    Если нет, вызывает исключение HTTPException 403.
    """
    if x_webhook_token != settings.WEBHOOK_SECRET_TOKEN:
        raise HTTPException(status_code=403, detail="Неверный или отсутствующий X-Webhook-Token")

# --- Создание маршрутизатора ---

# Все эндпоинты в этом роутере будут требовать валидный токен
# и будут иметь префикс /api/v1
router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(verify_token)],
    tags=["Webhook API"]
)


# --- Эндпоинты ---

@router.post("/webhook/rank-resumes", status_code=202)
async def webhook_rank_resumes(
    request: WebhookRankRequest,
    background_tasks: BackgroundTasks
):
    """
    Принимает запрос на ранжирование резюме, запускает фоновую задачу
    и немедленно возвращает ответ.
    """
    background_tasks.add_task(process_ranking_request, request)
    return {"status": "accepted", "message": "Задача по ранжированию резюме принята в обработку."}


@router.post("/webhook/analyze-interview", status_code=202)
async def webhook_analyze_interview(
    request: WebhookAnalysisRequest,
    background_tasks: BackgroundTasks
):
    """
    Принимает запрос на анализ интервью, запускает фоновую задачу
    и немедленно возвращает ответ.
    """
    background_tasks.add_task(process_analysis_request, request)
    return {"status": "accepted", "message": "Задача по анализу интервью принята в обработку."}
