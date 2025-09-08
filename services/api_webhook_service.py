
"""
Сервис для обработки фоновых задач, инициированных через новое Webhook API v1.
"""

import logging
import json

from sqlalchemy.ext.asyncio import AsyncSession

# Импорт моделей запросов
from api.schemas import (
    WebhookRankRequest,
    WebhookInterviewRequest,
    WebhookBuildVacancyRequest,
    WebhookAddVacancyRequest,
    WebhookGenerateTagsRequest
)

# Импорт существующих сервисов
from services.ai_services import score_and_sort_resumes, build_vacancy_description, question_gen_chain
from services.candidate_service import save_ranking_results
from services.webhook_service import send_webhook # Переиспользуем функцию отправки
from core.config import settings

# Импорт новых AI сервисов для API
from services.api_ai_services import generate_tags_for_vacancy, run_interview_simulation


async def process_ranking_request_v1(request: WebhookRankRequest, db: AsyncSession):
    """Фоновая задача для ранжирования резюме с учетом весов."""
    logging.info(f"[API Webhook] Запуск v1 задачи ранжирования для {request.webhook_url}")
    try:
        resumes_data = [{'id': r.filename, 'text': r.content} for r in request.resumes]
        
        # Здесь должна быть логика передачи weights в score_and_sort_resumes
        # Текущая реализация score_and_sort_resumes не принимает weights, нужно будет это учесть.
        # Пока вызываем как есть.
        sorted_results = await score_and_sort_resumes(request.vacancy_text, resumes_data)
        
        final_payload = {"results": sorted_results}
        await send_webhook(url=str(request.webhook_url), data=final_payload, secret=settings.WEBHOOK_SECRET_TOKEN)
    except Exception as e:
        logging.error(f"[API Webhook] Сбой v1 задачи ранжирования: {e}", exc_info=True)
        await send_webhook(url=str(request.webhook_url), data={"error": str(e)}, secret=settings.WEBHOOK_SECRET_TOKEN)

async def process_interview_simulation_request(request: WebhookInterviewRequest):
    """Фоновая задача для полной симуляции интервью."""
    logging.info(f"[API Webhook] Запуск задачи симуляции интервью для {request.webhook_url}")
    try:
        result = await run_interview_simulation(request.vacancy_text, request.resume_text)
        await send_webhook(url=str(request.webhook_url), data=result, secret=settings.WEBHOOK_SECRET_TOKEN)
    except Exception as e:
        logging.error(f"[API Webhook] Сбой задачи симуляции интервью: {e}", exc_info=True)
        await send_webhook(url=str(request.webhook_url), data={"error": str(e)}, secret=settings.WEBHOOK_SECRET_TOKEN)

async def process_vacancy_build_request(request: WebhookBuildVacancyRequest):
    """Фоновая задача для конструктора вакансий."""
    logging.info(f"[API Webhook] Запуск задачи конструктора вакансий для {request.webhook_url}")
    try:
        # Конвертируем веса в нужный формат, если это необходимо
        weights_for_service = {
            key: {"weight": value, "description": ""} for key, value in request.weights.items()
        }
        description = await build_vacancy_description(request.base_text, weights_for_service)
        await send_webhook(url=str(request.webhook_url), data={"description": description}, secret=settings.WEBHOOK_SECRET_TOKEN)
    except Exception as e:
        logging.error(f"[API Webhook] Сбой задачи конструктора вакансий: {e}", exc_info=True)
        await send_webhook(url=str(request.webhook_url), data={"error": str(e)}, secret=settings.WEBHOOK_SECRET_TOKEN)

async def process_add_vacancy_request(request: WebhookAddVacancyRequest, db: AsyncSession):
    """Фоновая задача для добавления вакансии и кандидатов в БД."""
    logging.info(f"[API Webhook] Запуск задачи добавления вакансии и кандидатов для {request.webhook_url}")
    try:
        # 1. Генерируем вопросы для вакансии
        generated_questions = await question_gen_chain.apredict(vacancy_text=request.vacancy_content)

        # 2. Формируем "псевдо-результаты" скоринга, чтобы использовать существующий сервис
        scored_resumes = []
        for r in request.resumes:
            scored_resumes.append({
                "filename": r.filename,
                "resume_text": r.content,
                "score": 0, # Начальный скор 0, т.к. мы их не оценивали
                "summary": "Кандидат добавлен через API.",
                "keywords": []
            })

        # 3. Сохраняем в БД через существующий сервис
        saved_candidates = await save_ranking_results(
            db=db,
            vacancy_text=request.vacancy_content,
            generated_questions=generated_questions,
            weights=None, # Веса не передаются в этом сценарии
            scored_resumes=scored_resumes
        )
        
        # Получаем ID вакансии из первого сохраненного кандидата (у всех он будет один)
        vacancy_id = saved_candidates[0].get('vacancy_id') if saved_candidates else None

        final_payload = {
            "message": "Вакансия и кандидаты успешно добавлены",
            "vacancy_id": vacancy_id
        }
        await send_webhook(url=str(request.webhook_url), data=final_payload, secret=settings.WEBHOOK_SECRET_TOKEN)
    except Exception as e:
        logging.error(f"[API Webhook] Сбой задачи добавления вакансии: {e}", exc_info=True)
        await send_webhook(url=str(request.webhook_url), data={"error": str(e)}, secret=settings.WEBHOOK_SECRET_TOKEN)

async def process_tag_generation_request(request: WebhookGenerateTagsRequest):
    """Фоновая задача для генерации тегов."""
    logging.info(f"[API Webhook] Запуск задачи генерации тегов для {request.webhook_url}")
    try:
        tags = await generate_tags_for_vacancy(request.vacancy_text)
        await send_webhook(url=str(request.webhook_url), data={"tags": tags}, secret=settings.WEBHOOK_SECRET_TOKEN)
    except Exception as e:
        logging.error(f"[API Webhook] Сбой задачи генерации тегов: {e}", exc_info=True)
        await send_webhook(url=str(request.webhook_url), data={"error": str(e)}, secret=settings.WEBHOOK_SECRET_TOKEN)
