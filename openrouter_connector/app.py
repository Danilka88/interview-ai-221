from flask import Flask, request, jsonify
import requests
import os
from dotenv import load_dotenv
import json
import re
from datetime import datetime, timezone

load_dotenv() # Загружаем переменные окружения из .env

app = Flask(__name__)

# Получаем API ключ из переменных окружения
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Словарь для маппинга имён моделей
MODEL_MAPPING = {
    "gemma3:4b": "google/gemma-3-27b-it:free",
    "qwen2.5-coder:3b": "google/gemma-3-12b-it:free", # Модель для AI-кандидата
    "another_model:123": "another_openrouter_model"
}

def extract_json_from_content(content: str) -> str | None:
    """
    Извлекает строку JSON из ответа LLM, который может содержать Markdown.
    """
    # Попытка 1: Ищем JSON-блок в Markdown-формате
    match = re.search(r"""```json
(.*?)
```""", content, re.DOTALL)
    if match:
        print(f"[{os.getpid()}] Found JSON block in Markdown.")
        return match.group(1)

    # Попытка 2: Ищем JSON, который начинается с '{' и заканчивается '}'
    try:
        start = content.index('{')
        end = content.rindex('}') + 1
        substring = content[start:end]
        json.loads(substring) # Проверяем валидность
        print(f"[{os.getpid()}] Found JSON block by slicing from {{ to }}.")
        return substring
    except (ValueError, json.JSONDecodeError):
        pass # Идем дальше, если не нашли или невалидный JSON

    # Попытка 3: Пробуем распарсить весь content как JSON
    try:
        json.loads(content)
        print(f"[{os.getpid()}] Content is directly parsable as JSON.")
        return content
    except json.JSONDecodeError:
        print(f"[{os.getpid()}] No valid JSON found in content.")
        return None

def create_error_json_content(summary: str, original_text: str = "") -> str:
    """
    Создает строку JSON с сообщением об ошибке для возврата клиенту.
    """
    error_content = {
        "score": -1,
        "summary": f"{summary}. Оригинальный текст: {original_text[:200]}...",
        "keywords": ["ОШИБКА_КОННЕКТОРА"]
    }
    return json.dumps(error_content)

@app.route("/api/chat", methods=["POST"])
def proxy_request():
    print(f"[{os.getpid()}] Incoming request to /api/chat")
    if not OPENROUTER_API_KEY:
        print(f"[{os.getpid()}] Error: OPENROUTER_API_KEY not set.")
        return jsonify({"error": "OPENROUTER_API_KEY not set in environment variables"}), 500

    try:
        data = request.json
        ollama_model_name = data.get("model")
        is_json_format_requested = data.get("format") == "json"
        print(f"[{os.getpid()}] Requested Ollama model: {ollama_model_name}, JSON format: {is_json_format_requested}")

        openrouter_model_name = MODEL_MAPPING.get(ollama_model_name, ollama_model_name)
        if openrouter_model_name != ollama_model_name:
            print(f"[{os.getpid()}] Mapped Ollama model '{ollama_model_name}' to OpenRouter model '{openrouter_model_name}'")
        else:
            print(f"[{os.getpid()}] Warning: Model '{ollama_model_name}' not found in MODEL_MAPPING. Using as is.")
        
        data["model"] = openrouter_model_name

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        openrouter_url = "https://openrouter.ai/api/v1/chat/completions"
        
        print(f"[{os.getpid()}] Sending request to OpenRouter with model: {data.get('model')}")
        
        # Отправляем запрос
        response_from_openrouter = requests.post(openrouter_url, json=data, headers=headers)
        
        print(f"[{os.getpid()}] Received response from OpenRouter with status code: {response_from_openrouter.status_code}")

        if response_from_openrouter.status_code != 200:
            print(f"[{os.getpid()}] Error from OpenRouter: {response_from_openrouter.text}")
            return jsonify(response_from_openrouter.json()), response_from_openrouter.status_code

        openrouter_json = response_from_openrouter.json()
        
        final_content_str = ""
        original_content = ""

        if "choices" in openrouter_json and len(openrouter_json["choices"]) > 0:
            original_content = openrouter_json["choices"][0]["message"]["content"]
            
            if is_json_format_requested:
                # Если клиент просил JSON, мы должны его извлечь
                extracted_json = extract_json_from_content(original_content)
                if extracted_json:
                    # Проверяем валидность извлеченного JSON
                    try:
                        json.loads(extracted_json)
                        final_content_str = extracted_json
                        print(f"[{os.getpid()}] Successfully extracted and validated JSON content.")
                    except json.JSONDecodeError:
                        final_content_str = create_error_json_content("LLM вернул невалидный JSON", extracted_json)
                        print(f"[{os.getpid()}] Extracted content is not valid JSON. Replaced with error JSON.")
                else:
                    # Если JSON не найден вообще
                    final_content_str = create_error_json_content("LLM вернул не-JSON ответ", original_content)
                    print(f"[{os.getpid()}] No parsable JSON found in content. Replaced with error JSON.")
            else:
                # Если клиент не просил JSON, используем оригинальный ответ как есть
                final_content_str = original_content
                print(f"[{os.getpid()}] JSON format not requested. Using original content.")
        else:
            # Если в ответе нет 'choices'
            final_content_str = create_error_json_content("Ответ от OpenRouter не содержит поля 'choices'", str(openrouter_json))
            print(f"[{os.getpid()}] OpenRouter response is missing 'choices'.")

        # --- Трансформация в формат Ollama ---
        ollama_compatible_response = {
            "model": ollama_model_name, # Возвращаем то имя, которое запрашивал клиент
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "message": {
                "role": "assistant",
                "content": final_content_str
            },
            "done": True,
            "total_duration": openrouter_json.get("usage", {}).get("total_tokens", 0) * 1000000, # Примерное значение
            "load_duration": 1000000, # Примерное значение
            "prompt_eval_count": openrouter_json.get("usage", {}).get("prompt_tokens", 0),
            "prompt_eval_duration": 500000000, # Примерное значение
            "eval_count": openrouter_json.get("usage", {}).get("completion_tokens", 0),
            "eval_duration": openrouter_json.get("usage", {}).get("total_tokens", 0) * 500000, # Примерное значение
        }
        
        print(f"[{os.getpid()}] Transformed response to Ollama format.")
        # print(f"[{os.getpid()}] Final response to client: {json.dumps(ollama_compatible_response, indent=2)}")

        return jsonify(ollama_compatible_response), 200

    except requests.exceptions.RequestException as req_e:
        print(f"[{os.getpid()}] Network or OpenRouter API error: {req_e}")
        return jsonify({"error": f"Network or OpenRouter API error: {req_e}"}), 502
    except Exception as e:
        print(f"[{os.getpid()}] An unexpected error occurred: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=11434)