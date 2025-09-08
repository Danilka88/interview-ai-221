
import logging
import json
from langchain_community.chat_models import ChatOllama
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain

from core.config import settings
from prompts.tag_prompts import TAG_CLOUD_PROMPT_TEMPLATE
from prompts.interview_prompts import (
    INTERVIEWER_SYSTEM_PROMPT,
    INTERVIEW_PLAN,
    CANDIDATE_SYSTEM_PROMPT,
    CANDIDATE_INFO_BLOCK,
    RECOMMENDED_QUESTIONS_BLOCK,
    DEFAULT_JOB_DESCRIPTION
)
# Импортируем существующие, уже настроенные цепочки и LLM
from services.ai_services import (
    analyst_chain,
    question_gen_chain,
    interviewer_llm,
    candidate_llm
)

# --- Инициализация LLM для API ---
# Модель для генерации тегов (текстовый вывод)
tag_gen_llm = ChatOllama(model=settings.LLM_QUESTION_GEN_MODEL, temperature=0.1)

# --- Цепочки для API ---
tag_gen_chain = LLMChain(
    llm=tag_gen_llm,
    prompt=PromptTemplate.from_template(TAG_CLOUD_PROMPT_TEMPLATE),
    verbose=False
)

async def generate_tags_for_vacancy(vacancy_text: str) -> str:
    """
    Генерирует строку тегов для вакансии с помощью LLM.
    """
    logging.info(f"[API AI Service] Начинаю генерацию тегов для вакансии: {vacancy_text[:50]}...")
    try:
        tags = await tag_gen_chain.apredict(vacancy_text=vacancy_text)
        logging.info(f"[API AI Service] Теги успешно сгенерированы: {tags}")
        return tags.strip()
    except Exception as e:
        logging.error(f"[API AI Service] Ошибка при генерации тегов: {e}", exc_info=True)
        raise

async def run_interview_simulation(vacancy_text: str, resume_text: str) -> dict:
    """
    Проводит полную симуляцию текстового интервью и возвращает его анализ.
    """
    logging.info("[API AI Service] Запуск полной симуляции интервью...")

    # 1. Подготовка контекста для интервью
    if not vacancy_text: vacancy_text = DEFAULT_JOB_DESCRIPTION
    if not resume_text: resume_text = "Резюме не предоставлено."

    try:
        generated_questions = await question_gen_chain.apredict(vacancy_text=vacancy_text)
    except Exception as e:
        logging.error(f"[API AI Service] Ошибка при подготовке контекста для симуляции: {e}", exc_info=True)
        generated_questions = "Вопросы не сгенерированы из-за ошибки."


    # 2. Формирование системных промптов для участников
    interviewer_prompt_template = (
        INTERVIEWER_SYSTEM_PROMPT +
        INTERVIEW_PLAN +
        CANDIDATE_INFO_BLOCK.format(candidate_profile=resume_text) +
        RECOMMENDED_QUESTIONS_BLOCK.format(generated_questions=generated_questions) +
        "\n\nТекущий диалог:\n{chat_history}\n\nКандидат: {human_input}\nAI-Рекрутер:"
    )

    candidate_prompt_template = (
        CANDIDATE_SYSTEM_PROMPT.format(resume_text=resume_text) +
        "\n\nТекущий диалог:\n{chat_history}\n\nAI-Рекрутер: {human_input}\nКандидат:"
    )

    # 3. Создание цепочек для диалога
    interviewer_chain = LLMChain(
        llm=interviewer_llm,
        prompt=PromptTemplate(template=interviewer_prompt_template, input_variables=["chat_history", "human_input"]),
        verbose=False
    )
    candidate_chain = LLMChain(
        llm=candidate_llm,
        prompt=PromptTemplate(template=candidate_prompt_template, input_variables=["chat_history", "human_input"]),
        verbose=False
    )

    # 4. Проведение симуляции
    chat_history = []
    # Начинаем с общего приветствия, чтобы AI-рекрутер сам сформулировал первый вопрос по инструкции
    interviewer_message = "Здравствуйте!"
    max_turns = 8 # Ограничим диалог, чтобы избежать бесконечного цикла

    try:
        for turn in range(max_turns):
            # Рекрутер задает вопрос
            if turn > 0: # На первом ходу сообщение уже есть
                 interviewer_message = await interviewer_chain.apredict(
                    chat_history="\n".join(chat_history),
                    human_input=chat_history[-1] # Последний ответ кандидата
                )
            else: # Первый ход рекрутера
                interviewer_message = await interviewer_chain.apredict(
                    chat_history="",
                    human_input="Начните собеседование."
                )


            logging.info(f"[API AI Service] Симуляция, ход {turn + 1}/{max_turns}. Рекрутер: {interviewer_message}")
            chat_history.append(f"AI-Рекрутер: {interviewer_message}")

            # Проверяем, не завершил ли рекрутер диалог
            if "завершить" in interviewer_message.lower():
                break

            # Кандидат отвечает
            candidate_response = await candidate_chain.apredict(
                chat_history="\n".join(chat_history),
                human_input=interviewer_message
            )
            logging.info(f"[API AI Service] Симуляция, ход {turn + 1}/{max_turns}. Кандидат: {candidate_response}")
            chat_history.append(f"Кандидат: {candidate_response}")

    except Exception as e:
        logging.error(f"[API AI Service] Ошибка во время симуляции диалога: {e}", exc_info=True)
        chat_history.append(f"Системная ошибка: {e}")


    logging.info("[API AI Service] Симуляция интервью завершена. Начинаю анализ.")

    # 5. Анализ результатов
    try:
        dialogue_log = "\n".join(chat_history)
        # Веса не передаются в этом сценарии, поэтому используем пустой JSON-объект
        analysis_json_str = await analyst_chain.apredict(
            vacancy_text=vacancy_text,
            resume_text=resume_text,
            dialogue_log=dialogue_log,
            weights_json="{}"
        )
        analysis_data = json.loads(analysis_json_str)
        logging.info("[API AI Service] Анализ интервью завершен.")
    except Exception as e:
        logging.error(f"[API AI Service] Ошибка при анализе симуляции: {e}", exc_info=True)
        analysis_data = {"error": "Не удалось проанализировать диалог.", "details": str(e)}


    return {
        "chat_history": [log.replace("AI-Рекрутер:", "Interviewer:").replace("Кандидат:", "Candidate:") for log in chat_history],
        "analysis": analysis_data
    }
