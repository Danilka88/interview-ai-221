
"""
Модели данных (Pydantic) для валидации запросов к Webhook API v1.
"""

from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Dict, Any

# --- Модели для эндпоинтов из WEBHOOK_API.md ---

class WebhookBase(BaseModel):
    """Базовая модель для всех вебхук-запросов."""
    webhook_url: HttpUrl = Field(..., description="URL, на который будет отправлен POST-запрос с результатом.")

class ResumeItem(BaseModel):
    """Модель для одного резюме в API запросе."""
    filename: str = Field(..., description="Имя файла резюме, которое будет возвращено в ответе.")
    content: str = Field(..., description="Полный текст резюме.")

class WebhookRankRequest(WebhookBase):
    """Модель запроса для асинхронного ранжирования резюме (с весами)."""
    vacancy_text: str = Field(..., description="Полный текст вакансии.")
    resumes: List[ResumeItem] = Field(..., description="Список объектов резюме для ранжирования.")
    weights: Optional[Dict[str, Any]] = Field(None, description="Словарь с весами критериев для оценки.")

class WebhookInterviewRequest(WebhookBase):
    """Модель запроса для полной симуляции интервью."""
    vacancy_text: str = Field(..., description="Полный текст вакансии.")
    resume_text: str = Field(..., description="Полный текст резюме.")

class WebhookBuildVacancyRequest(WebhookBase):
    """Модель запроса для конструктора вакансий."""
    base_text: str = Field(..., description="Ищем python-разраба. FastAPI, Postgres. Удаленка.")
    weights: Dict[str, Any] = Field(..., description="Словарь с весами критериев.")

class WebhookAddVacancyRequest(WebhookBase):
    """Модель запроса для добавления вакансии и кандидатов в БД."""
    vacancy_filename: str
    vacancy_content: str
    resumes: List[ResumeItem]

class WebhookGenerateTagsRequest(WebhookBase):
    """Модель запроса для генерации тегов по тексту вакансии."""
    vacancy_text: str = Field(..., description="Текст вакансии для извлечения тегов.")
