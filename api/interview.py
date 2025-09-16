import json
import logging
import asyncio
from typing import List, Optional
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from vosk import KaldiRecognizer

from sqlalchemy.ext.asyncio import AsyncSession

from core.models import InterviewLog, AnalysisRequest
from core.database import get_db
from services.ai_services import analyst_chain, create_llm_chain, interviewer_llm, candidate_llm, summarize_vacancy_tech_requirements
from services.candidate_service import save_interview_result
# Обновленный импорт
from services.voice_processing import get_vosk_model, silero_tts_instance, SAMPLE_RATE, text_to_speech
from prompts.interview_prompts import DEFAULT_JOB_DESCRIPTION, INTERVIEW_PLAN, CANDIDATE_SYSTEM_PROMPT, STRESS_CANDIDATE_SYSTEM_PROMPT, CANDIDATE_INFO_BLOCK, RECOMMENDED_QUESTIONS_BLOCK, INTERVIEWER_SYSTEM_PROMPT

router = APIRouter()

@router.post("/analyze-interview")
async def analyze_interview_endpoint(data: AnalysisRequest, db: AsyncSession = Depends(get_db)):
    try:
        history_str = "\n".join([f"{log.sender}: {log.text}" for log in data.conversation_history])
        logging.info("Начинаю единый комплексный анализ...")

        prompt_variables = {
            "vacancy_text": (data.vacancy_text or DEFAULT_JOB_DESCRIPTION),
            "resume_text": (data.resume_text or "Резюме не предоставлено."),
            "dialogue_log": history_str,
            "weights_json": json.dumps(data.weights, ensure_ascii=False, indent=2) if data.weights else "{}"
        }

        analysis_str = await analyst_chain.apredict(**prompt_variables)
        logging.info("Анализ завершен. Парсинг JSON...")
        
        clean_json_str = analysis_str.strip()
        # Попытка найти JSON-блок, если LLM добавил лишний текст или маркеры
        json_match = re.search(r'```json\n(.*)```', clean_json_str, re.DOTALL)
        if json_match:
            clean_json_str = json_match.group(1).strip()
        else:
            # Если маркеры не найдены, попробуем найти первый и последний { }
            json_match = re.search(r'\{.*\}', clean_json_str, re.DOTALL)
            if json_match:
                clean_json_str = json_match.group(0).strip()
            else:
                logging.warning("Не удалось найти валидный JSON-блок в ответе LLM.")
                raise ValueError("Ответ LLM не содержит валидного JSON.")
        
        analysis_json = json.loads(clean_json_str)

        # Сохраняем результат в БД
        await save_interview_result(
            db=db, 
            candidate_id=data.candidate_id, 
            # TODO: Определять тип интервью более надежно
            interview_type="voice/simulation", 
            report=analysis_json
        )

        return analysis_json


    except Exception as e:
        logging.error(f"Ошибка при полном анализе собеседования: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"error": "Ошибка на сервере при выполнении анализа."})

def _escape_braces(text: str) -> str:
    if not text:
        return ""
    return text.replace("{", "{{").replace("}", "}}")

def _create_interviewer_template(vacancy_text: str, resume_text: Optional[str], generated_questions: Optional[str]) -> str:
    logging.info(f"vacancy_text: {vacancy_text!r}")
    logging.info(f"resume_text: {resume_text!r}")
    logging.info(f"generated_questions: {generated_questions!r}")

    # Экранируем фигурные скобки в пользовательских данных
    safe_resume_text = _escape_braces(resume_text)
    safe_vacancy_text = _escape_braces(vacancy_text)
    safe_generated_questions = _escape_braces(generated_questions)

    final_candidate_block = CANDIDATE_INFO_BLOCK.format(candidate_profile=safe_resume_text) if resume_text else ""
    final_questions_block = RECOMMENDED_QUESTIONS_BLOCK.format(generated_questions=safe_generated_questions) if generated_questions else ""

    template = (
        f"{INTERVIEWER_SYSTEM_PROMPT}\n"
        f"{final_candidate_block}\n"
        f"{final_questions_block}\n\n"
        f"Вот описание вакансии, на которую претендует кандидат:\n{safe_vacancy_text}\n\n"
        f"Ты должен провести собеседование строго по следующему плану:\n{INTERVIEW_PLAN}\n\n"
        "Текущий диалог:\n{chat_history}\nКандидат: {human_input}\nТвой следующий вопрос:"
    )
    return template

@router.websocket("/ws/test")
async def websocket_test_endpoint(websocket: WebSocket):
    await websocket.accept()
    logging.info("Клиент для СИМУЛЯЦИИ подключен.")

    try:
        initial_data = await websocket.receive_json()
        if initial_data.get("type") != "start_interview":
            await websocket.close()
            return

        resume_text = initial_data.get("resume_text")
        if not resume_text:
            await websocket.send_json({"type": "error", "data": "Для запуска симуляции необходимо загрузить резюме кандидата."})
            await websocket.close()
            return

        vacancy_text = initial_data.get("vacancy_text") or DEFAULT_JOB_DESCRIPTION
        generated_questions = initial_data.get("generated_questions", "")

        interviewer_template = _create_interviewer_template(vacancy_text, resume_text, generated_questions)
        interviewer_chain = create_llm_chain(interviewer_llm, interviewer_template)

        candidate_template = f'''{CANDIDATE_SYSTEM_PROMPT.format(resume_text=resume_text)}

Текущий диалог:
{{chat_history}}
Интервьюер: {{human_input}}
Твой ответ:'''
        candidate_chain = create_llm_chain(candidate_llm, candidate_template)

        chat_history = []
        await websocket.send_json({"type": "status", "data": "Симуляция начинается... Интервьюер готовит первый вопрос."})
        question = await interviewer_chain.apredict(human_input="Начни собеседование, представившись и обозначив вакансию и ключевые темы для обсуждения.", chat_history="")
        await websocket.send_json({"type": "text", "sender": "Interviewer", "data": question})
        chat_history.append(f"Interviewer: {question}")

        for _ in range(15):
            history_str = "\n".join(chat_history)
            await websocket.send_json({"type": "status", "data": "Кандидат обдумывает ответ..."})
            answer = await candidate_chain.apredict(human_input=question, chat_history=history_str)
            await websocket.send_json({"type": "text", "sender": "Candidate", "data": answer})
            chat_history.append(f"Candidate: {answer}")

            if len(chat_history) > 20:
                question = "Спасибо, у меня на этом все. Нажмите кнопку «Завершить», чтобы закончить собеседование."
            else:
                history_str = "\n".join(chat_history)
                await websocket.send_json({"type": "status", "data": "Интервьюер анализирует ответ..."})
                question = await interviewer_chain.apredict(human_input=answer, chat_history=history_str)
            
            await websocket.send_json({"type": "text", "sender": "Interviewer", "data": question})
            chat_history.append(f"Interviewer: {question}")

            if "Нажмите кнопку «Завершить»" in question:
                break
        
        await websocket.send_json({"type": "status", "data": "Симуляция завершена."})
        await websocket.close()

    except WebSocketDisconnect:
        logging.info("Клиент для симуляции отключен.")
    except Exception as e:
        logging.error(f"Ошибка в WebSocket (симуляция): {e}", exc_info=True)
        # Попытка отправить сообщение об ошибке клиенту, если соединение еще открыто
        if not websocket.client_state.value == 3: # 3 is DISCONNECTED state
            await websocket.send_json({"type": "error", "message": "Произошла внутренняя ошибка сервера."})


@router.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket):
    await websocket.accept()
    logging.info("Клиент для голосового чата подключен.")

    initial_data = await websocket.receive_json()
    if initial_data.get("type") != "start_interview":
        await websocket.close()
        return

    language_code = initial_data.get("language", "ru")
    logging.info(f"Запрошен язык распознавания: {language_code}")

    vosk_model = get_vosk_model(language_code)

    if not vosk_model or not silero_tts_instance:
        error_msg = f"Модель Vosk для языка '{language_code}' не найдена на сервере. Убедитесь, что она скачана и размещена в папке 'vosk-models/vosk-model-{language_code}'."
        logging.error(error_msg)
        await websocket.send_json({"type": "error", "message": error_msg})
        await websocket.close()
        return

    recognizer = KaldiRecognizer(vosk_model, SAMPLE_RATE)
    
    try:
        vacancy_text = initial_data.get("vacancy_text") or DEFAULT_JOB_DESCRIPTION
        resume_text = initial_data.get("resume_text")
        generated_questions = initial_data.get("generated_questions", "")

        # Извлекаем только технические требования из вакансии для интервьюера
        summarized_vacancy_tech = await summarize_vacancy_tech_requirements(vacancy_text)

        interviewer_template = _create_interviewer_template(summarized_vacancy_tech, None, generated_questions)
        session_chain = create_llm_chain(interviewer_llm, interviewer_template)
        chat_history = []

        await websocket.send_json({"type": "status", "data": "Контекст загружен. ИИ-интервьюер готовит первый вопрос..."})
        question = await session_chain.apredict(human_input="Начни собеседование, представившись и обозначив вакансию и ключевые темы для обсуждения.", chat_history="")
        chat_history.append(f"Interviewer: {question}")
        
        await websocket.send_json({"type": "status", "data": "Вопрос сформирован. Преобразую текст в голос..."})
        logging.info(f"Интервьюер (LLM): {question}")
        await websocket.send_json({"type": "text", "sender": "Interviewer", "data": question})
        
        audio_b64 = await text_to_speech(question, silero_tts_instance)
        await websocket.send_json({"type": "audio", "data": audio_b64 or ""})

        while True:
            data = await websocket.receive_bytes()

            if not data:
                final_result_json = recognizer.FinalResult()
                final_text = json.loads(final_result_json).get('text', '')
                
                if final_text:
                    logging.info(f"Распознано (финал): {final_text}")
                    await websocket.send_json({"type": "text", "sender": "User", "data": final_text})
                    chat_history.append(f"User: {final_text}")
                    
                    await websocket.send_json({"type": "status", "data": "Ответ получен. Анализирую полноту информации..."})
                    history_str = "\n".join(chat_history)
                    question = await session_chain.apredict(human_input=final_text, chat_history=history_str)
                    chat_history.append(f"Interviewer: {question}")
                    
                    await websocket.send_json({"type": "status", "data": "Вопрос сформирован. Преобразую текст в голос..."})
                    audio_b64 = await text_to_speech(question, silero_tts_instance)

                    logging.info(f"Интервьюер (LLM): {question}")
                    await websocket.send_json({"type": "text", "sender": "Interviewer", "data": question})
                    await websocket.send_json({"type": "audio", "data": audio_b64 or ""})
                else:
                    logging.info("Ничего не распознано в финальном результате.")
                    await websocket.send_json({"type": "audio", "data": ""}) 
                continue

            recognizer.AcceptWaveform(data)
            partial_result = json.loads(recognizer.PartialResult())
            partial_text = partial_result.get('partial', '')
            if partial_text:
                await websocket.send_json({"type": "partial_text", "data": partial_text})

    except WebSocketDisconnect:
        logging.info("Клиент для голосового чата отключен.")
    except Exception as e:
        logging.error(f"Ошибка в WebSocket (live): {e}", exc_info=True)
        # Попытка отправить сообщение об ошибке клиенту, если соединение еще открыто
        if not websocket.client_state.value == 3: # 3 is DISCONNECTED state
            await websocket.send_json({"type": "error", "message": "Произошла внутренняя ошибка сервера."})

@router.websocket("/ws/stress_test")
async def websocket_stress_test_endpoint(websocket: WebSocket):
    await websocket.accept()
    logging.info("Клиент для СТРЕСС-ТЕСТ СИМУЛЯЦИИ подключен.")

    try:
        initial_data = await websocket.receive_json()
        if initial_data.get("type") != "start_interview":
            await websocket.close()
            return

        resume_text = initial_data.get("resume_text")
        if not resume_text:
            await websocket.send_json({"type": "error", "data": "Для запуска симуляции необходимо загрузить резюме кандидата."})
            await websocket.close()
            return

        vacancy_text = initial_data.get("vacancy_text") or DEFAULT_JOB_DESCRIPTION
        generated_questions = initial_data.get("generated_questions", "")

        interviewer_template = _create_interviewer_template(vacancy_text, resume_text, generated_questions)
        interviewer_chain = create_llm_chain(interviewer_llm, interviewer_template)

        candidate_template = f'''{STRESS_CANDIDATE_SYSTEM_PROMPT.format(resume_text=resume_text)}

Текущий диалог:
{{chat_history}}
Интервьюер: {{human_input}}
Твой ответ:'''
        candidate_chain = create_llm_chain(candidate_llm, candidate_template)

        chat_history = []
        await websocket.send_json({"type": "status", "data": "Стресс-тест симуляция начинается... Интервьюер готовит первый вопрос."})
        question = await interviewer_chain.apredict(human_input="Начни собеседование, представившись и обозначив вакансию и ключевые темы для обсуждения.", chat_history="")
        await websocket.send_json({"type": "text", "sender": "Interviewer", "data": question})
        chat_history.append(f"Interviewer: {question}")

        for _ in range(15):
            history_str = "\n".join(chat_history)
            await websocket.send_json({"type": "status", "data": "Кандидат обдумывает ответ..."})
            answer = await candidate_chain.apredict(human_input=question, chat_history=history_str)
            await websocket.send_json({"type": "text", "sender": "Candidate", "data": answer})
            chat_history.append(f"Candidate: {answer}")

            if len(chat_history) > 20:
                question = "Спасибо, у меня на этом все. Нажмите кнопку «Завершить», чтобы закончить собеседование."
            else:
                history_str = "\n".join(chat_history)
                await websocket.send_json({"type": "status", "data": "Интервьюер анализирует ответ..."})
                question = await interviewer_chain.apredict(human_input=answer, chat_history=history_str)
            
            await websocket.send_json({"type": "text", "sender": "Interviewer", "data": question})
            chat_history.append(f"Interviewer: {question}")

            if "Нажмите кнопку «Завершить»" in question:
                break
        
        await websocket.send_json({"type": "status", "data": "Симуляция завершена."})
        await websocket.close()

    except WebSocketDisconnect:
        logging.info("Клиент для стресс-тест симуляции отключен.")
    except Exception as e:
        logging.error(f"Ошибка в WebSocket (стресс-тест симуляция): {e}", exc_info=True)
        if not websocket.client_state.value == 3: # 3 is DISCONNECTED state
            await websocket.send_json({"type": "error", "message": "Произошла внутренняя ошибка сервера."})
