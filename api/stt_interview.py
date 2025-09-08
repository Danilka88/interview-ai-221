import json
import logging
import asyncio
from typing import List, Optional
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import InterviewLog, AnalysisRequest
from core.database import get_db
from services.ai_services import analyst_chain, create_llm_chain, interviewer_llm, summarize_vacancy_tech_requirements
from services.candidate_service import save_interview_result
from services.voice_processing import silero_tts_instance, text_to_speech
from prompts.interview_prompts import DEFAULT_JOB_DESCRIPTION, INTERVIEW_PLAN, CANDIDATE_INFO_BLOCK, RECOMMENDED_QUESTIONS_BLOCK, INTERVIEWER_SYSTEM_PROMPT

from services.stt_service import get_current_stt_provider, recognize_audio_stream
from core.settings_manager import settings_manager # To get current STT provider settings

router = APIRouter()

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

@router.websocket("/ws/live_stt")
async def websocket_live_stt_endpoint(websocket: WebSocket):
    await websocket.accept()
    logging.info("Клиент для голосового чата (STT-enabled) подключен.")

    initial_data = await websocket.receive_json()
    if initial_data.get("type") != "start_interview":
        await websocket.close()
        return

    language_code = initial_data.get("language", "ru")
    logging.info(f"Запрошен язык распознавания: {language_code}")

    current_stt_provider = get_current_stt_provider()
    logging.info(f"Используется STT провайдер: {settings_manager.stt_settings.STT_PROVIDER}")

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
            # This part will use the new STT service
            await recognize_audio_stream(websocket, current_stt_provider, language_code)
            
            # After recognition, get the final text from the websocket message history
            # This is a simplification; in a real scenario, recognize_audio_stream
            # would return the final text or push it to a queue.
            # For now, assume the last 'text' message from 'User' is the one we need.
            # This will require a more robust way to get the recognized text from the stream.
            # For demonstration, I'll assume the client sends a 'final_text' message after recognition.

            # A more robust approach would be to have recognize_audio_stream yield results
            # or use a shared queue/event system. For this example, I'll make a simplifying assumption.

            # Let's assume the client sends a specific message type for final recognized text
            # after the audio stream ends.
            
            # For now, I'll just simulate getting the final text.
            # In a real implementation, the `recognize_audio_stream` would handle sending
            # partial and final results back to the client, and this loop would then
            # receive the final text from the client or a shared state.

            # Receive the final recognized text from the client (sent by JS after user stops speaking)
            user_input_message = await websocket.receive_json()
            if user_input_message.get("type") == "final_user_text":
                final_text = user_input_message.get("data", "")
            else:
                logging.warning("Unexpected message type received from client after STT stream.")
                continue # Or handle error

            if final_text:
                logging.info(f"Распознано (финал): {final_text}")
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

    except WebSocketDisconnect:
        logging.info("Клиент для голосового чата (STT-enabled) отключен.")
    except Exception as e:
        logging.error(f"Ошибка в WebSocket (live_stt): {e}", exc_info=True)
        if not websocket.client_state.value == 3: # 3 is DISCONNECTED state
            await websocket.send_json({"type": "error", "message": "Произошла внутренняя ошибка сервера."})
