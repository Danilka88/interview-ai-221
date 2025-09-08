import logging
import json
import asyncio
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pathlib import Path

from services.stt_service import get_current_stt_provider, recognize_audio_stream
from services.voice_processing import silero_tts_instance, text_to_speech
from services.ai_services import create_llm_chain, interviewer_llm, summarize_vacancy_tech_requirements
from prompts.interview_prompts import DEFAULT_JOB_DESCRIPTION, INTERVIEW_PLAN, CANDIDATE_INFO_BLOCK, RECOMMENDED_QUESTIONS_BLOCK, INTERVIEWER_SYSTEM_PROMPT

from audio_processing.config import audio_processing_settings_manager
from audio_processing.processor import process_audio_for_noise_reduction

router = APIRouter()

# Pydantic model for incoming audio processing settings
class AudioProcessingConfigUpdate(BaseModel):
    AUDIO_PROCESSING_ENABLED: bool
    NOISE_REDUCTION_RATE: float

# --- HTML Page Endpoint ---
@router.get("/audio-processing/settings", response_class=HTMLResponse)
async def get_audio_processing_settings_page():
    """Serves the audio processing settings HTML page."""
    return Path("audio_processing/settings.html").read_text(encoding="utf-8")

# --- API Endpoints for Settings ---
@router.get("/api/v1/audio-processing/config")
async def get_audio_processing_config():
    """Returns the current audio processing configuration."""
    return audio_processing_settings_manager.settings.model_dump()

@router.post("/api/v1/audio-processing/config")
async def update_audio_processing_config(config_update: AudioProcessingConfigUpdate):
    """Updates the audio processing configuration at runtime."""
    try:
        audio_processing_settings_manager.update_settings(config_update.model_dump())
        logging.info(f"Audio processing settings updated at runtime: {config_update.model_dump()}")
        return {"message": "Audio processing settings updated successfully."}
    except Exception as e:
        logging.error(f"Error updating audio processing settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update audio processing settings: {e}")

# --- New WebSocket Endpoint with Audio Processing ---

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

@router.websocket("/ws/live_processed")
async def websocket_live_processed_endpoint(websocket: WebSocket):
    await websocket.accept()
    logging.info("Клиент для голосового чата (с обработкой аудио) подключен.")

    initial_data = await websocket.receive_json()
    if initial_data.get("type") != "start_interview":
        await websocket.close()
        return

    language_code = initial_data.get("language", "ru")
    logging.info(f"Запрошен язык распознавания: {language_code}")

    current_stt_provider = get_current_stt_provider()
    audio_processing_enabled = audio_processing_settings_manager.settings.AUDIO_PROCESSING_ENABLED
    noise_reduction_rate = audio_processing_settings_manager.settings.NOISE_REDUCTION_RATE
    sample_rate = 16000 # Предполагаем 16kHz для аудио

    try:
        vacancy_text = initial_data.get("vacancy_text") or DEFAULT_JOB_DESCRIPTION
        resume_text = initial_data.get("resume_text")
        generated_questions = initial_data.get("generated_questions", "")

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
            # Receive audio chunks from client
            audio_chunk = await websocket.receive_bytes()

            if audio_processing_enabled:
                # Apply noise reduction
                processed_audio_chunk = await process_audio_for_noise_reduction(
                    audio_chunk, sample_rate, noise_reduction_rate
                )
            else:
                processed_audio_chunk = audio_chunk

            # Send processed audio to STT provider
            # This part needs to be adapted to how `recognize_audio_stream` works.
            # `recognize_audio_stream` expects to receive bytes directly from the websocket.
            # We need to simulate that or refactor `recognize_audio_stream` to accept a byte chunk.
            # For now, I'll adapt the logic here to directly use the STT provider's methods.

            recognizer_instance = current_stt_provider.get_recognizer(language_code)
            
            if not processed_audio_chunk: # End of stream or empty chunk
                final_text = await current_stt_provider.get_final_result(recognizer_instance)
                if final_text:
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

            partial_text = await current_stt_provider.recognize_audio_chunk(recognizer_instance, processed_audio_chunk)
            if partial_text:
                await websocket.send_json({"type": "partial_text", "data": partial_text})

    except WebSocketDisconnect:
        logging.info("Клиент для голосового чата (с обработкой аудио) отключен.")
    except Exception as e:
        logging.error(f"Ошибка в WebSocket (live_processed): {e}", exc_info=True)
        if not websocket.client_state.value == 3: # 3 is DISCONNECTED state
            await websocket.send_json({"type": "error", "message": "Произошла внутренняя ошибка сервера."})
