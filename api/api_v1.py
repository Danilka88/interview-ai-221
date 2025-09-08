
"""
Эндпоинты для Webhook API v1.

Этот модуль реализует все асинхронные эндпоинты, описанные в WEBHOOK_API.md.
"""

import logging
from fastapi import APIRouter, Depends, Header, HTTPException, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_db

# Модели для валидации
from api.schemas import (
    WebhookRankRequest,
    WebhookInterviewRequest,
    WebhookBuildVacancyRequest,
    WebhookAddVacancyRequest,
    WebhookGenerateTagsRequest
)

# Фоновые задачи
from services.api_webhook_service import (
    process_ranking_request_v1,
    process_interview_simulation_request,
    process_vacancy_build_request,
    process_add_vacancy_request,
    process_tag_generation_request
)

# Создаем роутер для API v1
router = APIRouter(prefix="/api/v1/webhook")

# --- Зависимость для проверки токена --- #

async def verify_webhook_token(x_webhook_token: str = Header(...)):
    """Проверяет, что токен в заголовке совпадает с токеном из настроек."""
    if x_webhook_token != settings.WEBHOOK_SECRET_TOKEN:
        logging.warning(f"[API-AUTH] Неверный токен доступа: {x_webhook_token}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook token"
        )

# --- Эндпоинты --- #

@router.post("/rank-resumes", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(verify_webhook_token)])
async def rank_resumes_webhook(
    request: WebhookRankRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Принимает запрос на ранжирование резюме и запускает фоновую задачу."""
    logging.info(f"[API] Принят запрос на ранжирование для {request.webhook_url}")
    background_tasks.add_task(process_ranking_request_v1, request, db)
    return {"message": "Ranking task accepted and is being processed in the background."}

@router.post("/start-interview", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(verify_webhook_token)])
async def start_interview_webhook(
    request: WebhookInterviewRequest,
    background_tasks: BackgroundTasks
):
    """Принимает запрос на симуляцию интервью и запускает фоновую задачу."""
    logging.info(f"[API] Принят запрос на симуляцию интервью для {request.webhook_url}")
    background_tasks.add_task(process_interview_simulation_request, request)
    return {"message": "Interview simulation task accepted."}

@router.post("/build-vacancy", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(verify_webhook_token)])
async def build_vacancy_webhook(
    request: WebhookBuildVacancyRequest,
    background_tasks: BackgroundTasks
):
    """Принимает запрос на сборку вакансии и запускает фоновую задачу."""
    logging.info(f"[API] Принят запрос на сборку вакансии для {request.webhook_url}")
    background_tasks.add_task(process_vacancy_build_request, request)
    return {"message": "Vacancy build task accepted."}

@router.post("/add-vacancy-with-candidates", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(verify_webhook_token)])
async def add_vacancy_with_candidates_webhook(
    request: WebhookAddVacancyRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Принимает запрос на добавление вакансии и кандидатов в БД."""
    logging.info(f"[API] Принят запрос на добавление вакансии и кандидатов для {request.webhook_url}")
    background_tasks.add_task(process_add_vacancy_request, request, db)
    return {"message": "Add vacancy and candidates task accepted."}

@router.post("/generate-tags", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(verify_webhook_token)])
async def generate_tags_webhook(
    request: WebhookGenerateTagsRequest,
    background_tasks: BackgroundTasks
):
    """Принимает запрос на генерацию тегов и запускает фоновую задачу."""
    logging.info(f"[API] Принят запрос на генерацию тегов для {request.webhook_url}")
    background_tasks.add_task(process_tag_generation_request, request)
    return {"message": "Tag generation task accepted."}
