from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from pathlib import Path
import logging
import json

from services.file_processing import extract_text_from_file, save_upload_file_tmp, cleanup_file
from services.ai_services import question_gen_chain, build_vacancy_description, scoring_chain
from core.models import AnalysisRequest, VacancyBuildRequest, CriterionData
from prompts.interview_prompts import DEFAULT_JOB_DESCRIPTION

router = APIRouter()

@router.get("/")
async def get_index():
    return HTMLResponse(content=Path("dashboard.html").read_text(encoding="utf-8"))

@router.get("/test")
async def get_test():
    return HTMLResponse(content=Path("test.html").read_text(encoding="utf-8"))

@router.get("/result")
async def get_result():
    return HTMLResponse(content=Path("result.html").read_text(encoding="utf-8"))

@router.get("/dashboard")
async def get_dashboard_page():
    return HTMLResponse(content=Path("dashboard.html").read_text(encoding="utf-8"))

@router.get("/settings")
async def get_settings_page():
    return HTMLResponse(content=Path("settings.html").read_text(encoding="utf-8"))

@router.get("/vacancy_builder", response_class=HTMLResponse)
async def get_vacancy_builder():
    return Path("vacancy_builder/index.html").read_text(encoding="utf-8")

@router.get("/voice-interview")
async def get_voice_interview():
    return HTMLResponse(content=Path("index.html").read_text(encoding="utf-8"))

@router.get("/stt-voice-interview")
async def get_stt_voice_interview():
    return HTMLResponse(content=Path("stt_interview_page.html").read_text(encoding="utf-8"))

@router.post("/api/v1/build-vacancy-description")
async def api_build_vacancy_description(request: VacancyBuildRequest):
    try:
        description_text = await build_vacancy_description(
            vacancy_text=request.vacancy_text,
            weights=request.weights
        )
        return {"description": description_text}
    except Exception as e:
        logging.error(f"API call to build vacancy description failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при генерации описания вакансии: {e}")

@router.post("/upload-vacancy")
async def upload_vacancy_description(file: UploadFile = File(...)):
    tmp_path = await save_upload_file_tmp(file)
    text = await extract_text_from_file(tmp_path)
    cleanup_file(tmp_path)
    if not text:
        raise HTTPException(status_code=400, detail=f"Не удалось извлечь текст из файла {file.filename}.")
    
    generated_questions = ""
    try:
        logging.info("Начинаю генерацию вопросов по вакансии...")
        generated_questions = await question_gen_chain.apredict(vacancy_text=text)
        logging.info("Рекомендуемые вопросы по вакансии успешно сгенерированы.")
    except Exception as e:
        logging.error(f"Не удалось сгенерировать вопросы по вакансии: {e}")

    return {"filename": file.filename, "vacancy_text": text, "generated_questions": generated_questions}

@router.post("/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    tmp_path = await save_upload_file_tmp(file)
    text = await extract_text_from_file(tmp_path)
    cleanup_file(tmp_path)
    if not text:
        raise HTTPException(status_code=400, detail=f"Не удалось извлечь текст из файла {file.filename}.")
    return {"filename": file.filename, "resume_text": text}

@router.post("/analyze-scores")
async def analyze_scores(data: AnalysisRequest):
    """
    Анализирует диалог и возвращает только числовые оценки для графиков.
    """
    try:
        history_str = "\n".join([f"{log.sender}: {log.text}" for log in data.conversation_history])
        logging.info("Начинаю числовой анализ для графиков...")

        prompt_variables = {
            "vacancy_text": (data.vacancy_text or DEFAULT_JOB_DESCRIPTION),
            "resume_text": (data.resume_text or "Резюме не предоставлено."),
            "dialogue_log": history_str,
            "weights_json": json.dumps(data.weights, ensure_ascii=False, indent=2) if data.weights else "{}"
        }

        scores_str = await scoring_chain.apredict(**prompt_variables)
        logging.info(f"Числовой анализ завершен. Сырой ответ от LLM: {scores_str}")

        try:
            scores_json = json.loads(scores_str)
        except json.JSONDecodeError as json_e:
            logging.error(f"Ошибка парсинга JSON от LLM: {json_e}. Сырой ответ: '{scores_str}'", exc_info=True)
            raise HTTPException(status_code=500, detail={"error": "Ошибка парсинга ответа от AI."})
        
        return scores_json

    except Exception as e:
        logging.error(f"Ошибка при числовом анализе для графиков: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "Ошибка на сервере при расчете оценок."})
