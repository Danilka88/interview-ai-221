from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Dict, Any

# --- Модели для существующего веб-интерфейса ---

class InterviewLog(BaseModel):
    sender: str
    text: str

class AnalysisRequest(BaseModel):
    candidate_id: Optional[int] = None # ID кандидата из нашей БД
    conversation_history: List[InterviewLog]
    vacancy_text: Optional[str] = None
    resume_text: Optional[str] = None
    weights: Optional[Dict[str, Any]] = None

# --- Модели для нового Webhook API ---

class WebhookResumeItem(BaseModel):
    """Модель для одного резюме в API запросе."""
    id: str = Field(..., description="Уникальный идентификатор резюме, который будет возвращен в ответе.")
    text: str = Field(..., description="Полный текст резюме.")

class WebhookRankRequest(BaseModel):
    """Модель запроса для асинхронного ранжирования резюме."""
    webhook_url: HttpUrl = Field(..., description="URL, на который будет отправлен POST-запрос с результатом.")
    vacancy_text: str = Field(..., description="Полный текст вакансии.")
    resumes: List[WebhookResumeItem] = Field(..., description="Список объектов резюме для ранжирования.")

class WebhookAnalysisRequest(BaseModel):
    """Модель запроса для асинхронного анализа диалога."""
    webhook_url: HttpUrl = Field(..., description="URL, на который будет отправлен POST-запрос с результатом.")
    conversation_history: List[InterviewLog] = Field(..., description="История диалога для анализа.")
    vacancy_text: Optional[str] = Field(None, description="Полный текст вакансии (опционально).")
    resume_text: Optional[str] = Field(None, description="Полный текст резюме (опционально).")

# --- Модели для конструктора вакансий ---

class CriterionData(BaseModel):
    """Модель для одного критерия в конструкторе вакансий."""
    weight: int
    description: str

class VacancyBuildRequest(BaseModel):
    """Модель запроса для конструктора вакансий."""
    vacancy_text: str = Field(..., description="Исходный текст вакансии.")
    weights: Dict[str, Dict[str, Any]] = Field(..., description="Словарь с весами и описаниями критериев.")
