# MCP Server: Model Context Protocol (API-Driven Interview)

## 1. Обзор концепции

**MCP Server** — это специализированный сервер, который предоставляет доступ к различным AI-моделям и сложным многошаговым AI-воркфлоу через стандартизированный API. Он управляет контекстом (данными, промптами) для каждой задачи и взаимодействует с внешними системами асинхронно, используя вебхуки.

Данная реализация MCP Server фокусируется на сценарии автоматизированного интервью:
1.  Внешняя система (клиент) отправляет резюме пользователя.
2.  MCP Server находит наиболее подходящую вакансию из своей внутренней базы.
3.  MCP Server инициирует интервью, задавая вопросы пользователю через вебхуки.
4.  Внешняя система передает ответы пользователя обратно на MCP Server.
5.  MCP Server записывает ответы и продолжает диалог.

## 2. Ключевые принципы реализации

*   **Использование существующей функциональности:** MCP Server будет использовать уже реализованные сервисы (`services/ai_services.py`, `services/file_processing.py`) для работы с LLM, текстом и файлами.
*   **Отдельный блок:** MCP Server будет реализован как новый набор API-эндпоинтов и сервисов, не затрагивающий существующий веб-интерфейс.
*   **Асинхронное, многошаговое взаимодействие через вебхуки:** Интервью — это диалог. MCP Server будет отправлять вопросы через вебхуки и ожидать ответы через отдельные API-эндпоинты.
*   **Управление состоянием (Session Management):** Для каждого интервью будет создаваться сессия, в которой будет храниться вся история диалога, контекст (резюме, вакансия) и текущее состояние.
*   **Безопасность:** Все входящие запросы к MCP Server будут защищены токеном. Все исходящие вебхуки будут подписаны HMAC-подписью.
*   **База данных:** Для хранения вакансий и состояний интервью-сессий потребуется база данных.

## 3. Архитектурный обзор и компоненты

### 3.1. База данных

Для хранения вакансий и состояний интервью-сессий потребуется база данных. Для прототипа можно использовать SQLite, для продакшена — PostgreSQL.

**Предлагаемые таблицы:**

*   **`vacancies`**: Хранит информацию о вакансиях.
    *   `id` (UUID/INT, Primary Key)
    *   `title` (TEXT)
    *   `description` (TEXT) - полный текст вакансии
    *   `requirements` (TEXT, Optional)
    *   `responsibilities` (TEXT, Optional)
    *   `created_at` (DATETIME)
    *   `updated_at` (DATETIME)

*   **`interview_sessions`**: Хранит состояние каждого активного интервью.
    *   `id` (UUID, Primary Key)
    *   `resume_text` (TEXT) - текст резюме пользователя
    *   `vacancy_id` (UUID/INT, Foreign Key to `vacancies.id`) - ID вакансии, по которой идет интервью
    *   `conversation_history` (JSON) - массив объектов `{sender: str, text: str}`
    *   `current_question` (TEXT, Optional) - последний заданный вопрос
    *   `expected_answer_type` (TEXT, Optional) - тип ожидаемого ответа (например, "текст", "число")
    *   `webhook_url` (TEXT) - URL для отправки вебхуков по этой сессии
    *   `status` (TEXT) - "active", "waiting_for_answer", "completed", "failed"
    *   `created_at` (DATETIME)
    *   `updated_at` (DATETIME)

### 3.2. Новые Pydantic Модели (`core/models.py`)

Помимо уже существующих `WebhookRankRequest` и `WebhookAnalysisRequest`, потребуются новые модели для MCP-взаимодействия:

*   **`MCPStartInterviewRequest`**:
    *   `resume_text: str`
    *   `webhook_url: HttpUrl`
    *   `user_id: Optional[str]` (для идентификации пользователя во внешней системе)

*   **`MCPContinueInterviewRequest`**:
    *   `session_id: str`
    *   `user_answer: str`

*   **`MCPWebhookPayload`**: Базовая модель для всех исходящих вебхуков от MCP.
    *   `session_id: str`
    *   `type: str` ("question", "end", "error")
    *   `data: Dict` (содержимое зависит от `type`)

### 3.3. Новый Сервисный Слой (`services/mcp_service.py`)

Этот файл будет содержать всю бизнес-логику для MCP-сервера.

*   **`async def find_best_vacancy(resume_text: str) -> Dict`**:
    *   Запрашивает вакансии из БД.
    *   Использует `resume_scorer_chain` (из `services/ai_services.py`) для оценки соответствия резюме каждой вакансии.
    *   Возвращает наиболее подходящую вакансию (или ее ID).
*   **`async def create_interview_session(...)`**:
    *   Создает новую запись в `interview_sessions` в БД.
    *   Генерирует первый вопрос с помощью `interviewer_llm` (из `services/ai_services.py`).
    *   Отправляет первый вопрос через вебхук на `webhook_url`.
*   **`async def continue_interview_session(...)`**:
    *   Загружает состояние сессии из БД.
    *   Обновляет `conversation_history` ответом пользователя.
    *   Использует `interviewer_llm` для генерации следующего вопроса.
    *   Сохраняет обновленное состояние сессии в БД.
    *   Отправляет следующий вопрос через вебхук.
*   **`async def end_interview_session(...)`**:
    *   Загружает сессию.
    *   Использует `analyst_chain` (из `services/ai_services.py`) для финального анализа диалога.
    *   Сохраняет финальный анализ в сессии.
    *   Отправляет финальный результат через вебхук.
*   **`async def handle_mcp_error(...)`**: Универсальная функция для отправки вебхука с ошибкой.

### 3.4. Новый API-маршрутизатор (`api/mcp.py`)

Этот файл будет содержать эндпоинты для взаимодействия с MCP Server.

*   **`POST /api/v1/mcp/start_interview`**:
    *   Принимает `MCPStartInterviewRequest`.
    *   Запускает фоновую задачу (например, `background_tasks.add_task(mcp_service.create_interview_session, ...)`) 
    *   Возвращает `202 Accepted` с `session_id`.
*   **`POST /api/v1/mcp/continue_interview`**:
    *   Принимает `MCPContinueInterviewRequest`.
    *   Запускает фоновую задачу (`background_tasks.add_task(mcp_service.continue_interview_session, ...)`) 
    *   Возвращает `202 Accepted`.
*   **`GET /api/v1/mcp/session_status/{session_id}` (опционально)**:
    *   Позволяет внешней системе запросить текущий статус сессии.

### 3.5. Интеграция с существующим проектом

*   **`main.py`**: Будет импортировать и подключать новый `api/mcp.py` маршрутизатор.
*   **`services/ai_services.py`**: Возможно, потребуется добавить новые функции для LLM, специфичные для сопоставления вакансий.
*   **`requirements.txt`**: Добавить зависимости для работы с БД (например, `SQLAlchemy`, `asyncpg` или `aiosqlite`).

## 4. Сценарий взаимодействия (Webhook-Driven Interview)

### 4.1. Начало интервью

1.  **Внешняя система** отправляет `POST` запрос на `http://your-mcp-server.com/api/v1/mcp/start_interview` с `resume_text` и `webhook_url`.
    *   **Заголовки:** `Content-Type: application/json`, `X-Webhook-Token: ваш_секретный_токен`
    *   **Тело:**
        ```json
        {
          "resume_text": "Полный текст резюме пользователя...",
          "webhook_url": "https://your-laravel-app.com/mcp-webhook-receiver",
          "user_id": "user_abc123"
        }
        ```
2.  **MCP Server** немедленно отвечает `202 Accepted` с `session_id`.
    *   **Ответ:**
        ```json
        {
          "status": "accepted",
          "message": "Задача по началу интервью принята.",
          "session_id": "uuid_сессии_интервью"
        }
        ```
3.  **MCP Server (фоновая задача):**
    *   Находит лучшую вакансию для `resume_text`.
    *   Создает новую запись в `interview_sessions` в БД.
    *   Генерирует первый вопрос с помощью `interviewer_llm`.
    *   Отправляет `POST` запрос на `https://your-laravel-app.com/mcp-webhook-receiver`.
        *   **Заголовки:** `Content-Type: application/json`, `X-Webhook-Signature-256: sha256=подпись`
        *   **Тело:**
            ```json
            {
              "session_id": "uuid_сессии_интервью",
              "type": "question",
              "question": "Здравствуйте, расскажите о вашем опыте работы с Python?",
              "context": { "user_id": "user_abc123" } // Дополнительный контекст для внешней системы
            }
            ```

### 4.2. Продолжение интервью (вопрос-ответ)

1.  **Внешняя система** получает вебхук с вопросом.
2.  **Внешняя система** отображает вопрос пользователю, получает его ответ.
3.  **Внешняя система** отправляет `POST` запрос на `http://your-mcp-server.com/api/v1/mcp/continue_interview`.
    *   **Заголовки:** `Content-Type: application/json`, `X-Webhook-Token: ваш_секретный_токен`
    *   **Тело:**
        ```json
        {
          "session_id": "uuid_сессии_интервью",
          "user_answer": "Мой опыт работы с Python составляет 5 лет, в основном с веб-фреймворками."
        }
        ```
4.  **MCP Server** немедленно отвечает `202 Accepted`.
5.  **MCP Server (фоновая задача):**
    *   Загружает сессию из БД.
    *   Обновляет `conversation_history` ответом пользователя.
    *   Использует `interviewer_llm` для генерации следующего вопроса.
    *   Сохраняет обновленную сессию в БД.
    *   Отправляет следующий вопрос через вебхук.

### 4.3. Завершение интервью

1.  **MCP Server (фоновая задача):**
    *   Определяет, что интервью завершено (например, по количеству вопросов или по специальной фразе).
    *   Выполняет финальный анализ диалога с помощью `analyst_chain`.
    *   Сохраняет финальный анализ в сессии.
    *   Отправляет `POST` запрос на `https://your-laravel-app.com/mcp-webhook-receiver` с финальным результатом.
        *   **Тело:**
            ```json
            {
              "session_id": "uuid_сессии_интервью",
              "type": "end",
              "analysis_result": {
                "overall_score": 85,
                "summary": "Кандидат продемонстрировал глубокие знания...",
                "strengths": ["Опыт с FastAPI", "Асинхронное программирование"],
                "weaknesses": ["Неуверенные ответы по базам данных"],
                "recommendation": "Рекомендуется к следующему этапу."
              }
            }
            ```

### 4.4. Обработка ошибок

*   Если на любом этапе MCP Server сталкивается с критической ошибкой, он отправляет вебхук типа `"error"` на `webhook_url`.
    *   **Тело:**
        ```json
        {
          "session_id": "uuid_сессии_интервью",
          "type": "error",
          "message": "Описание произошедшей ошибки на сервере MCP."
        }
        ```
