import json
import logging
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from services.file_processing import extract_text_from_file, save_upload_file_tmp, cleanup_file
from services.ai_services import resume_scorer_chain
from services.candidate_service import save_ranking_results # Обновленный импорт
from core.database import get_db

router = APIRouter()

@router.get("/rank")
async def get_rank_page():
    return HTMLResponse(content=Path("ranking/rank.html").read_text(encoding="utf-8"))

@router.get("/rank/result")
async def get_rank_result_page():
    return HTMLResponse(content=Path("ranking/rank_result.html").read_text(encoding="utf-8"))

@router.get("/rank/interview")
async def get_rank_interview_page():
    return HTMLResponse(content=Path("ranking/interview.html").read_text(encoding="utf-8"))

@router.get("/rank/simulation")
async def get_rank_simulation_page():
    return HTMLResponse(content=Path("ranking/simulation.html").read_text(encoding="utf-8"))

@router.get("/rank/stress_simulation")
async def get_rank_stress_simulation_page():
    return HTMLResponse(content=Path("ranking/stress_simulation.html").read_text(encoding="utf-8"))

@router.get("/rank/interview_result")
async def get_rank_interview_result_page():
    return HTMLResponse(content=Path("ranking/interview_result.html").read_text(encoding="utf-8"))

@router.post("/rank-resumes")
async def rank_resumes(
    db: AsyncSession = Depends(get_db), 
    vacancy: UploadFile = File(...), 
    resumes: List[UploadFile] = File(...), 
    weights: str = Form(...),
    generated_questions: Optional[str] = Form(None) # Добавлено
):
    logging.info(f"Получен запрос на ранжирование. Вакансия: {vacancy.filename}, резюме: {len(resumes)} шт.")
    
    try:
        weights_data = json.loads(weights)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Некорректный формат данных весов.")
    
    try:
        vacancy_path = await save_upload_file_tmp(vacancy)
        vacancy_text = await extract_text_from_file(vacancy_path)
        cleanup_file(vacancy_path)
        if not vacancy_text:
            raise HTTPException(status_code=400, detail="Не удалось обработать файл вакансии.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка на сервере при обработке вакансии: {e}")

    scored_resumes = []
    for i, resume_file in enumerate(resumes, 1):
        logging.info(f"[Резюме {i}/{len(resumes)}] Обработка: {resume_file.filename}")
        resume_text = None
        try:
            resume_path = await save_upload_file_tmp(resume_file)
            resume_text = await extract_text_from_file(resume_path)
            cleanup_file(resume_path)
            if not resume_text:
                raise ValueError("Текст из файла не был извлечен.")

            score_str = await resume_scorer_chain.apredict(
                vacancy_text=vacancy_text,
                resume_text=resume_text,
                weights_json=json.dumps(weights_data, ensure_ascii=False, indent=2)
            )
            score_data = json.loads(score_str)
            
            score_data["filename"] = resume_file.filename
            score_data["resume_text"] = resume_text
            scored_resumes.append(score_data)

        except Exception as e:
            error_summary = f"Ошибка обработки файла: {e}"
            logging.error(f"[Резюме {i}/{len(resumes)}] Сбой: {resume_file.filename}. Причина: {error_summary}", exc_info=True)
            scored_resumes.append({
                "filename": resume_file.filename,
                "score": -1,
                "summary": error_summary,
                "keywords": ["ОШИБКА"],
                "resume_text": resume_text or "Текст не был извлечен."
            })
            continue
    
    # Сохраняем все в одной транзакции и обогащаем ID
    enriched_resumes = await save_ranking_results(
        db, 
        vacancy_text, 
        generated_questions, # Передаем сгенерированные вопросы
        weights_data, # Передаем веса
        scored_resumes
    )

    sorted_resumes = sorted(enriched_resumes, key=lambda x: x.get('score', 0), reverse=True)
    return {"ranking": sorted_resumes}