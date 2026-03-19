# План реализации Task 1: Call an LLM from Code

## LLM провайдер и модель

- **Провайдер**: Qwen Code API (развёрнут на VM через qwen-code-oai-proxy)
- **Модель**: `qwen3-coder-plus`
- **API**: OpenAI-совместимый endpoint (`/v1/chat/completions`)

## Архитектура агента

```
User question (CLI arg) → agent.py → HTTP POST → Qwen Code API → JSON response → stdout
                              ↑
                         .env.agent.secret
                         (LLM_API_KEY, LLM_API_BASE, LLM_MODEL)
```

## Компоненты

### 1. Загрузка конфигурации

- Читать `.env.agent.secret` через `pydantic-settings`
- Извлекать: `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL`
- Валидировать наличие всех полей

### 2. Парсинг аргументов

- Использовать `argparse`
- Принимать один позиционный аргумент — вопрос пользователя

### 3. HTTP запрос к LLM

- Метод: `POST`
- URL: `{LLM_API_BASE}/chat/completions`
- Headers: `Authorization: Bearer {LLM_API_KEY}`, `Content-Type: application/json`
- Body:

  ```json
  {
    "model": "qwen3-coder-plus",
    "messages": [{"role": "user", "content": "<question>"}]
  }
  ```

### 4. Обработка ответа

- Парсить JSON ответ от API
- Извлекать `choices[0].message.content`
- Форматировать выходной JSON:

  ```json
  {"answer": "<content>", "tool_calls": []}
  ```

### 5. Вывод

- **stdout**: только валидный JSON (одна строка)
- **stderr**: все отладочные сообщения, ошибки
- **exit code**: 0 при успехе

## Зависимости

- `httpx` — HTTP клиент (уже в `pyproject.toml`)
- `pydantic-settings` — загрузка конфига (уже в `pyproject.toml`)
- `argparse` — стандартная библиотека

## Тестирование

- 1 регрессионный тест: запустить `agent.py` с вопросом, проверить наличие полей `answer` и `tool_calls` в JSON

## Риски

- API недоступен — обрабатывать HTTP ошибки, выводить в stderr
- Таймаут — установить лимит 60 секунд
- Невалидный JSON от API — обрабатывать исключения
