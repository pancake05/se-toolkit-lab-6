# Plan: Task 3 — The System Agent

## Overview

В этой задаче я добавлю инструмент `query_api` к агенту из Task 2, чтобы он мог отправлять запросы к deployed backend и отвечать на вопросы о системе.

## Implementation Plan

### 1. Tool Schema: `query_api`

Добавлю новую функцию `query_api(method, path, body=None)`:

**Параметры:**
- `method` (string): HTTP метод (GET, POST, PUT, DELETE, etc.)
- `path` (string): путь к endpoint (например, `/items/`, `/analytics/completion-rate`)
- `body` (string, optional): JSON тело запроса для POST/PUT запросов

**Возвращает:** JSON string с `status_code` и `body`

**Аутентификация:** Использует `LMS_API_KEY` из `.env.docker.secret` (или переменных окружения)

### 2. Environment Variables

Нужно читать из окружения:
- `LMS_API_KEY` — ключ для аутентификации в backend API
- `AGENT_API_BASE_URL` — базовый URL backend (по умолчанию `http://localhost:42002`)

Обновлю `AgentSettings` или создам отдельный класс для этих настроек.

### 3. System Prompt Update

Обновлю системный промпт, чтобы LLM понимал, когда использовать:
- `read_file`/`list_files` — для чтения wiki и исходного кода
- `query_api` — для получения данных из running API (количество items, статус коды, analytics)

### 4. Implementation Steps

1. **Создать функцию `query_api`**:
   - Использовать `httpx` для HTTP запросов
   - Добавить заголовок `Authorization: Bearer {LMS_API_KEY}`
   - Обработать ошибки (timeout, HTTP errors)

2. **Обновить `get_tool_schemas()`**:
   - Добавить схему для `query_api`

3. **Обновить `TOOLS` словарь**:
   - Добавить `query_api: query_api`

4. **Обновить системный промпт**:
   - Описать третий инструмент
   - Объяснить, когда какой инструмент использовать

5. **Обновить загрузку env переменных**:
   - Читать `LMS_API_KEY` из `.env.docker.secret`
   - Читать `AGENT_API_BASE_URL` (с дефолтом)

### 5. Testing Strategy

Запущу `run_eval.py` и буду итеративно фиксить проблемы:

1. Сначала проверю базовые вопросы (wiki lookup)
2. Затем system facts (framework, ports)
3. Затем data queries (item count, scores)
4. Наконец, bug diagnosis вопросы

### 6. Expected Challenges

- **LLM может путать инструменты**: Нужно чётко описать в промпте разницу
- **Аутентификация**: Убедиться, что `LMS_API_KEY` передаётся правильно
- **CORS/Network**: Backend должен быть доступен на `AGENT_API_BASE_URL`

## Benchmark Results (to be filled after first run)

Initial score: _/10

First failures:
- [ ] ...

Iteration strategy:
1. Fix tool descriptions if LLM calls wrong tool
2. Fix tool implementation if errors occur
3. Adjust system prompt for clarity

## Notes

- Не hardcode значения — авточекер будет инжектить свои credentials
- Debug output в stderr, не в stdout
- Тесты должны проверять, что правильный инструмент был вызван
