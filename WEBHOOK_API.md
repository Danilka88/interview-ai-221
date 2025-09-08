# Документация по Webhook API для AI Interviewer

Версия API: 1.2

## 1. Общая концепция

API построено на основе механизма **вебхуков** для обработки длительных задач. Взаимодействие происходит в два этапа:

1.  **Запрос на запуск задачи**: Ваше приложение отправляет запрос на наш API, передавая все необходимые данные и `webhook_url`.
2.  **Мгновенный ответ**: Наш API немедленно отвечает статусом `202 Accepted`, подтверждая, что задача принята в обработку.
3.  **Обратный вызов (Webhook)**: Когда фоновая задача завершается, наш сервис отправляет `POST` запрос с готовым результатом на указанный вами `webhook_url`.

## 2. Аутентификация

Все запросы к API должны содержать заголовок `X-Webhook-Token` с секретным токеном.

- **Заголовок**: `X-Webhook-Token`
- **Значение**: Токен, указанный в переменной `WEBHOOK_SECRET_TOKEN` в файле `.env` нашего сервиса.

## 3. Проверка подписи вебхука (Безопасность)

Когда наш сервис отправляет результат на ваш `webhook_url`, он подписывает запрос, чтобы вы могли убедиться в его подлинности.

- **Заголовок подписи**: `X-AI-Interviewer-Signature`
- **Алгоритм**: HMAC-SHA256, где ключ — это ваш `WEBHOOK_SECRET_TOKEN`.

**Пример проверки подписи на стороне получателя (Python):**
```python
import hmac
import hashlib
import json

# Ваш секретный токен, который вы используете для вызова API
SECRET_TOKEN = "your-super-secret-and-long-token-here"

def verify_signature(request_body_bytes, signature_header):
    if not signature_header:
        return False
    
    hash_object = hmac.new(SECRET_TOKEN.encode('utf-8'), msg=request_body_bytes, digestmod=hashlib.sha256)
    expected_signature = hash_object.hexdigest()
    
    return hmac.compare_digest(expected_signature, signature_header)

# В вашем обработчике вебхука (например, в Laravel)
# request_body = request->getContent();
# signature = request->header('X-AI-Interviewer-Signature');
# is_valid = verify_signature(request_body, signature);
```

---

## 4. Эндпоинты

### 4.1 Ранжирование резюме

Запускает асинхронную задачу по оценке и ранжированию списка резюме относительно текста вакансии.

- **URL**: `POST /api/v1/webhook/rank-resumes`
- **Метод**: `POST`

**Тело запроса (Request Body):**

```json
{
  "webhook_url": "https://your-app.com/webhook-receiver",
  "vacancy_text": "Полный текст вакансии здесь...",
  "resumes": [
    {
      "filename": "cv_developer1.pdf",
      "content": "Текст первого резюме..."
    },
    {
      "filename": "cv_developer2.docx",
      "content": "Текст второго резюме..."
    }
  ],
  "weights": {
    "technical_skills": 5,
    "experience": 4
  }
}
```

**Структура ответа (Webhook Payload):**

На ваш `webhook_url` придет `POST` запрос со списком отранжированных резюме.

```json
{
  "results": [
    {
      "filename": "cv_developer1.pdf",
      "score": 85,
      "summary": "Отличный кандидат, полностью соответствует требованиям...",
      "pros": ["Опыт с FastAPI", "Знание PostgreSQL"],
      "cons": ["Мало опыта с Docker"]
    }
  ]
}
```

### 4.2 Симуляция интервью

Запускает асинхронную задачу для полной симуляции текстового интервью между AI-рекрутером и AI-кандидатом.

- **URL**: `POST /api/v1/webhook/start-interview`
- **Метод**: `POST`

**Тело запроса (Request Body):**

```json
{
    "webhook_url": "https://your-app.com/webhook-receiver-analysis",
    "vacancy_text": "Полный текст вакансии...",
    "resume_text": "Полный текст резюме..."
}
```

**Структура ответа (Webhook Payload):**

```json
{
    "chat_history": [
        "Interviewer: Здравствуйте, расскажите о своем опыте.",
        "Candidate: Я 5 лет работаю с Python..."
    ],
    "analysis": {
        "scores": {
            "technical_skills": 8,
            "experience_relevance": 9
        },
        "overall_score": 8.2,
        "summary": "Кандидат продемонстрировал глубокие знания...",
        "pros": ["Опыт с FastAPI"],
        "cons": ["Неуверенные ответы по базам данных"],
        "recommendation": "рекомендуется к следующему этапу"
    }
}
```

### 4.3 Конструктор вакансий

Запускает асинхронную задачу для генерации улучшенного описания вакансии на основе черновика и весов.

- **URL**: `POST /api/v1/webhook/build-vacancy`
- **Метод**: `POST`

**Тело запроса (Request Body):**

```json
{
    "webhook_url": "https://your-app.com/webhook-receiver-vacancy",
    "base_text": "Ищем python-разраба. FastAPI, Postgres. Удаленка.",
    "weights": {
        "technical_skills": 5,
        "experience": 5,
        "communication": 3,
        "problem_solving": 4,
        "teamwork": 3
    }
}
```

**Структура ответа (Webhook Payload):**

```json
{
    "description": "# Python-разработчик (Middle/Senior)\n\n## О проекте..."
}
```

### 4.4 Добавление вакансии и кандидатов

Запускает асинхронную задачу для сохранения новой вакансии и привязанных к ней кандидатов в базу данных AI Interviewer.

- **URL**: `POST /api/v1/webhook/add-vacancy-with-candidates`
- **Метод**: `POST`

**Тело запроса (Request Body):**

```json
{
    "webhook_url": "https://your-app.com/webhook-receiver-db",
    "vacancy_filename": "backend_dev_vacancy.txt",
    "vacancy_content": "Ищем опытного Backend-разработчика...",
    "resumes": [
        {
            "filename": "ivanov_cv.pdf",
            "content": "Иванов Иван, опыт 5 лет..."
        },
        {
            "filename": "petrov_cv.docx",
            "content": "Петров Петр, опыт 3 года..."
        }
    ]
}
```

**Структура ответа (Webhook Payload):**

```json
{
    "message": "Вакансия и кандидаты успешно добавлены",
    "vacancy_id": 123
}
```

### 4.5 Генерация тегов для вакансии

Запускает асинхронную задачу для извлечения из текста вакансии ключевых навыков, технологий и характеристик в виде облака тегов.

- **URL**: `POST /api/v1/webhook/generate-tags`
- **Метод**: `POST`

**Тело запроса (Request Body):**

```json
{
    "webhook_url": "https://your-app.com/webhook-receiver-tags",
    "vacancy_text": "Ищем опытного Python-разработчика для работы над финтех-проектом. Требуется знание FastAPI, PostgreSQL и Docker. Важна работа в команде и опыт с CI/CD."
}
```

**Структура ответа (Webhook Payload):**

На ваш `webhook_url` придет `POST` запрос со строкой тегов.

```json
{
    "tags": "Python, FastAPI, PostgreSQL, Docker, финтех, работа в команде, CI/CD, разработка API"
}
```
