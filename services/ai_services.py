import json
import logging
from typing import List, Dict

from langchain_community.chat_models import ChatOllama
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain

# Импорт настроек и промптов
from core.config import settings
from prompts.interview_prompts import QUESTION_GEN_PROMPT, VACANCY_TECH_SUMMARY_PROMPT
from prompts.analysis_prompts import ANALYST_SYSTEM_PROMPT
from prompts.ranking_prompts import RESUME_SCORER_PROMPT, VACANCY_BUILDER_PROMPT # Добавлено

# --- Инициализация LLM на основе настроек ---
interviewer_llm = ChatOllama(model=settings.LLM_INTERVIEWER_MODEL, temperature=0.7)
candidate_llm = ChatOllama(model=settings.LLM_CANDIDATE_MODEL, temperature=0.7)
question_gen_llm = ChatOllama(model=settings.LLM_QUESTION_GEN_MODEL, temperature=0.5)
# Модель для анализа и скоринга должна уметь работать с JSON
analyst_llm = ChatOllama(model=settings.LLM_ANALYST_MODEL, temperature=0.2, format="json")
# Новый LLM для генерации текста без JSON формата
text_llm = ChatOllama(model=settings.LLM_ANALYST_MODEL, temperature=0.2) # Без format="json"

# --- Инициализация цепочек LLM с использованием промптов ---
question_gen_chain = LLMChain(
    llm=question_gen_llm, 
    prompt=PromptTemplate.from_template(QUESTION_GEN_PROMPT),
    verbose=False
)

analyst_chain = LLMChain(
    llm=analyst_llm, 
    prompt=PromptTemplate.from_template(ANALYST_SYSTEM_PROMPT), 
    verbose=False
)

resume_scorer_chain = LLMChain(
    llm=analyst_llm, 
    prompt=PromptTemplate.from_template(RESUME_SCORER_PROMPT), 
    verbose=False
)

# Новая цепочка для конструктора вакансий
vacancy_builder_chain = LLMChain(
    llm=text_llm, # Используем text_llm
    prompt=PromptTemplate.from_template(VACANCY_BUILDER_PROMPT),
    verbose=False
)

# top_ranker_chain был удален для упрощения логики

vacancy_tech_summary_chain = LLMChain(
    llm=text_llm, # Используем text_llm, так как нам не нужен JSON
    prompt=PromptTemplate.from_template(VACANCY_TECH_SUMMARY_PROMPT),
    verbose=False
)


def create_llm_chain(llm_instance, template):
    """Фабричная функция для создания кастомных цепочек LLM для диалогов."""
    prompt = PromptTemplate(template=template, input_variables=["chat_history", "human_input"])
    return LLMChain(llm=llm_instance, prompt=prompt, verbose=False)


async def build_vacancy_description(vacancy_text: str, weights: Dict) -> str:
    """
    Генерирует улучшенное описание вакансии на основе текста вакансии и весов критериев.
    """
    logging.info(f"Начинаю генерацию описания вакансии с LLM для: {vacancy_text[:50]}...")
    try:
                # Преобразуем объекты CriterionData в простые словари для JSON сериализации
        processed_weights = {}
        for key, value in weights.items():
            # Предполагаем, что value - это объект, который имеет атрибуты 'weight' и 'description'
            # Если value - это уже словарь, то просто используем его
            if isinstance(value, dict):
                processed_weights[key] = value
            else:
                # Если value - это объект CriterionData, преобразуем его
                # Это предполагает, что CriterionData имеет атрибуты weight и description
                processed_weights[key] = {
                    "weight": value.weight,
                    "description": value.description
                }

        weights_json = json.dumps(processed_weights, ensure_ascii=False, indent=2)
        
        generated_description = await vacancy_builder_chain.apredict(
            vacancy_text=vacancy_text,
            weights_json=weights_json
        )
        logging.info("Описание вакансии успешно сгенерировано LLM.")
        return generated_description
    except Exception as e:
        logging.error(f"Ошибка при генерации описания вакансии LLM: {e}", exc_info=True)
        raise Exception(f"Ошибка при генерации описания вакансии: {e}")


async def score_and_sort_resumes(vacancy_text: str, resumes: List[Dict]) -> List[Dict]:
    """
    Асинхронно оценивает список резюме относительно вакансии и сортирует их.
    Обрабатывает ошибки для каждого резюме индивидуально.

    Args:
        vacancy_text: Текст вакансии.
        resumes: Список словарей, где каждый словарь содержит 'id' и 'text' резюме.

    Returns:
        Отсортированный список словарей с результатами скоринга.
    """
    scored_resumes = []
    for i, resume_data in enumerate(resumes, 1):
        resume_id = resume_data.get("id", f"unknown_{i}")
        resume_text = resume_data.get("text")
        logging.info(f"[Скоринг {i}/{len(resumes)}] Обработка резюме ID: {resume_id}")

        if not resume_text:
            logging.warning(f"[Скоринг {i}/{len(resumes)}] Пустой текст для резюме ID: {resume_id}. Пропуск.")
            scored_resumes.append({
                "id": resume_id,
                "filename": resume_id, # Для обратной совместимости с UI
                "score": -1,
                "summary": "Ошибка: Текст резюме пуст.",
                "keywords": ["ОШИБКА"],
            })
            continue

        try:
            score_str = await resume_scorer_chain.apredict(vacancy_text=vacancy_text, resume_text=resume_text)
            score_data = json.loads(score_str)
            score_data["id"] = resume_id
            score_data["filename"] = resume_id # Для обратной совместимости с UI
            scored_resumes.append(score_data)
            logging.info(f"[Скоринг {i}/{len(resumes)}] Резюме ID: {resume_id} успешно оценено.")
        except Exception as e:
            error_summary = f"Ошибка анализа ИИ: {e}"
            logging.error(f"[Скоринг {i}/{len(resumes)}] Сбой обработки резюме ID: {resume_id}. Причина: {error_summary}", exc_info=True)
            scored_resumes.append({
                "id": resume_id,
                "filename": resume_id, # Для обратной совместимости с UI
                "score": -1,
                "summary": error_summary,
                "keywords": ["ОШИБКА"],
            })
            continue
            
    # Сортируем по убыванию оценки. Ошибки (-1) окажутся в конце.
    sorted_resumes = sorted(scored_resumes, key=lambda x: x.get('score', 0), reverse=True)
    return sorted_resumes

async def summarize_vacancy_tech_requirements(vacancy_text: str) -> str:
    """
    Извлекает и суммирует ключевые технические и профессиональные требования из текста вакансии.
    """
    logging.info(f"Начинаю извлечение технических требований из вакансии: {vacancy_text[:50]}...")
    try:
        summary = await vacancy_tech_summary_chain.apredict(vacancy_text=vacancy_text)
        logging.info("Технические требования успешно извлечены.")
        return summary
    except Exception as e:
        logging.error(f"Ошибка при извлечении технических требований из вакансии: {e}", exc_info=True)
        return "Не удалось извлечь технические требования."
