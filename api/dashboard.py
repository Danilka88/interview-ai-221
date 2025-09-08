"""
API для получения данных для страницы Дашборда.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import OperationalError

from core.database import get_db
from core.schemas import Vacancy, Candidate, Interview

router = APIRouter()

@router.get("/dashboard/data")
async def get_dashboard_data(db: AsyncSession = Depends(get_db)):
    """Возвращает все вакансии с привязанными кандидатами и их интервью."""
    try:
        result = await db.execute(
            select(Vacancy)
            .options(
                selectinload(Vacancy.candidates)
                .selectinload(Candidate.interviews)
            )
            .order_by(Vacancy.created_at.desc())
        )
        vacancies = result.scalars().all()
        return vacancies
    except Exception as e:
        logging.error(f"Ошибка при получении данных для дашборда: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка сервера при загрузке данных для дашборда")

@router.put("/candidate/{candidate_id}/status")
async def update_candidate_status(candidate_id: int, status: str, db: AsyncSession = Depends(get_db)):
    """Обновляет статус кандидата (этап воронки найма)."""
    try:
        candidate = await db.get(Candidate, candidate_id)
        if not candidate:
            raise HTTPException(status_code=404, detail="Кандидат не найден")
        
        candidate.status = status
        await db.commit()
        logging.info(f"Статус кандидата ID {candidate_id} обновлен на '{status}'.")
        return {"message": f"Статус кандидата {candidate_id} обновлен на {status}"}
    except Exception as e:
        logging.error(f"Ошибка при обновлении статуса кандидата ID {candidate_id}: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Ошибка сервера при обновлении статуса")

@router.delete("/dashboard/data")
async def delete_all_data(db: AsyncSession = Depends(get_db)):
    """Удаляет все данные из всех таблиц и пересоздает их."""
    try:
        async with db.begin():
            await db.execute(text("DELETE FROM interviews"))
            await db.execute(text("DELETE FROM candidates"))
            await db.execute(text("DELETE FROM vacancies"))
            try:
                # Эта команда может вызвать ошибку, если таблица sqlite_sequence не существует (в пустой БД)
                await db.execute(text("DELETE FROM sqlite_sequence WHERE name IN ('interviews', 'candidates', 'vacancies')"))
            except OperationalError:
                logging.warning("Таблица sqlite_sequence не найдена (вероятно, база данных была пуста). Пропускаю сброс счетчиков.")
        
        logging.info("Все данные из таблиц были успешно удалены.")
        return {"message": "Все данные успешно удалены."}
    except Exception as e:
        logging.error(f"Ошибка при удалении всех данных: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Ошибка сервера при удалении данных")
