"""
Сервисный слой для выполнения операций с базой данных.
"""

import logging
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from core.schemas import Vacancy, Candidate, Interview

async def save_ranking_results(
    db: AsyncSession, 
    vacancy_text: str, 
    generated_questions: Optional[str], # Добавлено
    weights: Optional[Dict[str, Any]], # Добавлено
    scored_resumes: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Атомарно сохраняет вакансию и всех успешно отскоренных кандидатов в БД.
    Возвращает список кандидатов, обогащенный ID из базы данных.
    """
    try:
        # 1. Создаем вакансию
        title = vacancy_text[:100].strip() + "..." if len(vacancy_text) > 100 else vacancy_text.strip()
        new_vacancy = Vacancy(
            title=title, 
            text=vacancy_text,
            generated_questions=generated_questions, # Сохраняем сгенерированные вопросы
            weights_json=weights # Сохраняем веса
        )
        db.add(new_vacancy)
        await db.flush() # Получаем ID вакансии до коммита
        logging.info(f"Вакансия с ID {new_vacancy.id} добавлена в сессию.")

        # 2. Создаем кандидатов и добавляем их в сессию
        candidates_to_create = []
        for resume_data in scored_resumes:
            if resume_data.get("score", -1) != -1:
                candidate = Candidate(
                    filename=resume_data.get("filename", "unknown"),
                    resume_text=resume_data.get("resume_text", ""),
                    initial_score=resume_data.get("score"),
                    status="new",
                    vacancy_id=new_vacancy.id
                )
                candidates_to_create.append((candidate, resume_data))
                db.add(candidate)
        
        logging.info(f"{len(candidates_to_create)} кандидатов добавлено в сессию.")
        await db.flush() # Получаем ID для всех кандидатов

        # 3. Обогащаем исходные данные ID из БД
        for candidate, resume_data in candidates_to_create:
            resume_data['id'] = candidate.id

        # 4. Коммитим транзакцию
        await db.commit()
        logging.info("Транзакция по сохранению вакансии и кандидатов успешно завершена.")
        
        return scored_resumes

    except Exception as e:
        logging.error(f"Ошибка при сохранении результатов ранжирования в БД: {e}", exc_info=True)
        await db.rollback()
        # В случае ошибки возвращаем исходные данные без ID
        for resume in scored_resumes:
            resume['id'] = None
        return scored_resumes

async def save_interview_result(
    db: AsyncSession, 
    candidate_id: int, 
    interview_type: str, 
    report: dict
) -> Optional[Interview]:
    """Сохраняет результат анализа интервью в БД."""
    if not candidate_id:
        logging.warning("Попытка сохранить интервью без ID кандидата. Операция отменена.")
        return None
        
    new_interview = Interview(
        candidate_id=candidate_id,
        interview_type=interview_type,
        full_report_json=report,
        final_score=report.get("interview_analysis", {}).get("suitability_score")
    )
    db.add(new_interview)
    
    candidate = await db.get(Candidate, candidate_id)
    if candidate:
        candidate.status = "interview_completed"
        logging.info(f"Статус кандидата ID {candidate_id} обновлен на 'interview_completed'.")

    await db.commit()
    await db.refresh(new_interview)
    logging.info(f"Результат интервью ID {new_interview.id} для кандидата {candidate_id} сохранен.")
    return new_interview
