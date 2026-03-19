#!/usr/bin/env python3
"""
Agent CLI — отправляет вопрос в LLM и возвращает структурированный JSON ответ.

Использование:
    uv run agent.py "Ваш вопрос здесь"

Выход:
    JSON на stdout: {"answer": "...", "source": "...", "tool_calls": [...]}
    Все отладочные сообщения — в stderr
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    """
    Настройки агента из переменных окружения.

    Ожидает:
        LLM_API_KEY — API ключ провайдера
        LLM_API_BASE — базовый URL API endpoint
        LLM_MODEL — название модели
        LMS_API_KEY — ключ для аутентификации в backend API
        AGENT_API_BASE_URL — базовый URL backend (по умолчанию http://localhost:42002)
    """

    llm_api_key: str
    llm_api_base: str
    llm_model: str
    lms_api_key: str
    agent_api_base_url: str = "http://localhost:42002"

    model_config = SettingsConfigDict(
        # Читаем только из переменных окружения (не из .env файла)
        # Это нужно для работы авточекера, который инжектит свои credentials
        env_file=None,
    )


def parse_args() -> argparse.Namespace:
    """Парсит аргументы командной строки."""
    parser = argparse.ArgumentParser(description="Agent CLI — задайте вопрос LLM")
    parser.add_argument("question", type=str, help="Вопрос для LLM")
    return parser.parse_args()


def get_project_root() -> Path:
    """Возвращает корень проекта (где находится agent.py)."""
    return Path(__file__).parent.resolve()


def is_safe_path(path: str) -> tuple[bool, Path]:
    """
    Проверяет, что путь находится в пределах проекта.

    Args:
        path: Относительный путь от корня проекта

    Returns:
        Кортеж (безопасен ли путь, абсолютный путь)
    """
    project_root = get_project_root()
    # Разрешаем относительный путь
    absolute_path = (project_root / path).resolve()

    # Проверяем, что путь начинается с project_root
    try:
        absolute_path.relative_to(project_root)
        return True, absolute_path
    except ValueError:
        return False, absolute_path


def read_file(path: str) -> str:
    """
    Читает файл из проекта.

    Args:
        path: Относительный путь от корня проекта

    Returns:
        Содержимое файла или сообщение об ошибке
    """
    safe, absolute_path = is_safe_path(path)

    if not safe:
        return f"Ошибка: доступ за пределами проекта запрещён ({path})"

    if not absolute_path.exists():
        return f"Ошибка: файл не найден ({path})"

    if absolute_path.is_dir():
        return f"Ошибка: это директория, а не файл ({path})"

    try:
        with open(absolute_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Ошибка чтения файла: {e}"


def list_files(path: str) -> str:
    """
    Список файлов в директории.

    Args:
        path: Относительный путь от корня проекта

    Returns:
        Список файлов через \\n или сообщение об ошибке
    """
    safe, absolute_path = is_safe_path(path)

    if not safe:
        return f"Ошибка: доступ за пределами проекта запрещён ({path})"

    if not absolute_path.exists():
        return f"Ошибка: путь не найден ({path})"

    if not absolute_path.is_dir():
        return f"Ошибка: это файл, а не директория ({path})"

    try:
        entries = list(absolute_path.iterdir())
        # Сортируем: сначала директории, потом файлы
        entries.sort(key=lambda x: (not x.is_dir(), x.name))
        return "\n".join([e.name for e in entries])
    except Exception as e:
        return f"Ошибка чтения директории: {e}"


def query_api(
    method: str,
    path: str,
    body: str | None = None,
    settings: AgentSettings | None = None,
) -> str:
    """
    Отправляет HTTP запрос к backend API.

    Args:
        method: HTTP метод (GET, POST, PUT, DELETE, etc.)
        path: Путь к endpoint (например, /items/, /analytics/completion-rate)
        body: JSON тело запроса (опционально, для POST/PUT)
        settings: Настройки API (для аутентификации)

    Returns:
        JSON string с status_code и body ответа или сообщение об ошибке
    """
    if settings is None:
        # Пытаемся создать настройки, если не переданы
        try:
            settings = AgentSettings()
        except Exception as e:
            return f"Ошибка: не удалось загрузить настройки API: {e}"

    base_url = settings.agent_api_base_url.rstrip("/")
    url = f"{base_url}{path}"

    headers = {
        "Authorization": f"Bearer {settings.lms_api_key}",
        "Content-Type": "application/json",
    }

    print(f"Запрос к API: {method} {url}", file=sys.stderr)

    try:
        with httpx.Client(timeout=30.0) as client:
            if method.upper() in ("GET", "DELETE"):
                response = client.request(method.upper(), url, headers=headers)
            elif method.upper() in ("POST", "PUT", "PATCH"):
                if body:
                    try:
                        body_data = json.loads(body)
                    except json.JSONDecodeError:
                        return f"Ошибка: невалидный JSON в теле запроса: {body}"
                    response = client.request(
                        method.upper(), url, headers=headers, json=body_data
                    )
                else:
                    response = client.request(method.upper(), url, headers=headers)
            else:
                return f"Ошибка: неизвестный HTTP метод '{method}'"

            result = {
                "status_code": response.status_code,
                "body": response.text,
            }
            return json.dumps(result, ensure_ascii=False)

    except httpx.ConnectError as e:
        return f"Ошибка подключения к API ({url}): {e}"
    except httpx.TimeoutException as e:
        return f"Таймаут запроса к API ({url}): {e}"
    except httpx.HTTPError as e:
        return f"HTTP ошибка при запросе к API: {e}"
    except Exception as e:
        return f"Неожиданная ошибка при запросе к API: {e}"


# Словарь доступных инструментов
TOOLS = {
    "read_file": read_file,
    "list_files": list_files,
    "query_api": query_api,
}


def get_tool_schemas() -> list[dict[str, Any]]:
    """
    Возвращает схемы инструментов для function calling.

    Returns:
        Список схем инструментов в формате OpenAI
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Читает содержимое файла из проекта. Используйте для чтения документации, кода и других файлов.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Относительный путь к файлу от корня проекта (например, 'wiki/git-workflow.md')",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "Список файлов и директорий в указанной директории проекта. Используйте для навигации по структуре проекта.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Относительный путь к директории от корня проекта (например, 'wiki')",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_api",
                "description": "Отправляет HTTP запрос к backend API. Используйте для получения данных из running системы: количество items, статус коды, analytics, и т.д.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "description": "HTTP метод: GET, POST, PUT, DELETE, etc.",
                        },
                        "path": {
                            "type": "string",
                            "description": "Путь к endpoint (например, '/items/', '/analytics/completion-rate')",
                        },
                        "body": {
                            "type": "string",
                            "description": "JSON тело запроса (опционально, для POST/PUT запросов)",
                        },
                    },
                    "required": ["method", "path"],
                },
            },
        },
    ]


def get_system_prompt() -> str:
    """
    Возвращает системный промпт для агента.

    Returns:
        Текст системного промпта
    """
    return """Вы — System Agent, помогающий пользователям находить информацию в проекте.

У вас есть три инструмента:
1. list_files(path) —列出 файлы в директории проекта
2. read_file(path) — прочитать содержимое файла из проекта
3. query_api(method, path, body) — отправить HTTP запрос к backend API

Когда какой инструмент использовать:
- list_files: для навигации по структуре проекта (wiki/, backend/, и т.д.)
- read_file: для чтения документации (wiki/), исходного кода (.py файлы), конфигурации (docker-compose.yml, Dockerfile)
- query_api: для получения данных из running backend системы:
  - Количество items в базе данных: GET /items/
  - Статус коды ответов: запросы к API без авторизации
  - Analytics данные: /analytics/* endpoints
  - Информация о learners: /learners/* endpoints

Порядок работы:
1. Определите тип вопроса:
   - Wiki/documentation вопрос → используйте list_files и read_file
   - System facts (framework, ports) → read_file для чтения кода/конфигов
   - Data queries (сколько items, scores) → query_api
   - Bug diagnosis → query_api для получения ошибки, затем read_file для поиска бага в коде
2. Используйте нужные инструменты для сбора информации
3. В ответе укажите:
   - answer: краткий ответ на вопрос
   - source: путь к файлу или "api" для данных из API

Если вопрос не связан с проектом, ответьте своими знаниями и укажите source: "general".

Всегда включайте source в ваш финальный ответ. Формат: {"answer": "...", "source": "..."}
"""


def call_llm(
    messages: list[dict[str, Any]],
    tool_schemas: list[dict[str, Any]] | None = None,
    settings: AgentSettings | None = None,
) -> dict[str, Any]:
    """
    Отправляет сообщения в LLM и возвращает ответ.

    Args:
        messages: Список сообщений в формате OpenAI
        tool_schemas: Схемы инструментов (опционально)
        settings: Настройки API

    Returns:
        Словарь с ответом API
    """
    url = f"{settings.llm_api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    payload: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
    }

    if tool_schemas:
        payload["tools"] = tool_schemas

    print(f"Отправка запроса к {url}...", file=sys.stderr)

    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()

    data = response.json()
    print(f"Получен ответ от LLM", file=sys.stderr)

    return data


def execute_tool(
    tool_name: str, args: dict[str, Any], settings: AgentSettings | None = None
) -> str:
    """
    Выполняет инструмент по имени.

    Args:
        tool_name: Имя инструмента
        args: Аргументы для инструмента
        settings: Настройки API (для query_api)

    Returns:
        Результат выполнения инструмента
    """
    if tool_name not in TOOLS:
        return f"Ошибка: неизвестный инструмент '{tool_name}'"

    func = TOOLS[tool_name]
    try:
        # Вызываем функцию с аргументами
        # query_api требует settings, остальные - нет
        if tool_name == "query_api":
            return func(**args, settings=settings)
        else:
            return func(**args)
    except TypeError as e:
        return f"Ошибка вызова инструмента: {e}"
    except Exception as e:
        return f"Ошибка выполнения инструмента: {e}"


def extract_source_from_answer(answer: str, messages: list[dict[str, Any]]) -> str:
    """
    Извлекает source из ответа или генерирует его на основе tool_calls.

    Args:
        answer: Текст ответа
        messages: История сообщений

    Returns:
        Строка source
    """
    # Пытаемся найти упоминание файла в ответе
    import re

    # Паттерн для поиска ссылок на markdown файлы
    pattern = r"wiki/[\w\-/]+\.md(?:#[\w\-]+)?"
    match = re.search(pattern, answer)
    if match:
        return match.group(0)

    # Если есть tool_calls с read_file, используем последний прочитанный файл
    for msg in reversed(messages):
        if msg.get("role") == "tool":
            # Пытаемся извлечь путь из инструмента
            tool_call_id = msg.get("tool_call_id", "")
            # Ищем соответствующий tool_call
            for prev_msg in messages:
                if prev_msg.get("role") == "assistant":
                    tool_calls = prev_msg.get("tool_calls", [])
                    for tc in tool_calls:
                        if (
                            tc.get("id") == tool_call_id
                            and tc.get("function", {}).get("name") == "read_file"
                        ):
                            args = json.loads(
                                tc.get("function", {}).get("arguments", "{}")
                            )
                            path = args.get("path", "")
                            if path:
                                return path

    return "general"


def run_agentic_loop(question: str, settings: AgentSettings) -> dict[str, Any]:
    """
    Запускает агентовый цикл с LLM.

    Args:
        question: Вопрос пользователя
        settings: Настройки API

    Returns:
        Словарь с answer, source и tool_calls
    """
    max_iterations = 10
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": get_system_prompt()},
        {"role": "user", "content": question},
    ]
    tool_calls_log: list[dict[str, Any]] = []

    for iteration in range(max_iterations):
        print(f"Итерация {iteration + 1}/{max_iterations}", file=sys.stderr)

        # Отправляем запрос к LLM
        response_data = call_llm(
            messages=messages,
            tool_schemas=get_tool_schemas(),
            settings=settings,
        )

        assistant_message = response_data["choices"][0]["message"]

        # Проверяем, есть ли tool_calls
        tool_calls = assistant_message.get("tool_calls", [])

        if not tool_calls:
            # LLM вернул финальный ответ без tool_calls
            answer = assistant_message.get("content", "")
            source = extract_source_from_answer(answer, messages)

            return {
                "answer": answer,
                "source": source,
                "tool_calls": tool_calls_log,
            }

        # Добавляем сообщение assistant с tool_calls в историю
        messages.append(assistant_message)

        # Выполняем каждый tool_call
        for tool_call in tool_calls:
            tool_call_id = tool_call.get("id")
            function = tool_call.get("function", {})
            tool_name = function.get("name", "")
            arguments_str = function.get("arguments", "{}")

            try:
                args = json.loads(arguments_str)
            except json.JSONDecodeError:
                args = {}

            print(f"Выполнение инструмента: {tool_name}({args})", file=sys.stderr)

            # Выполняем инструмент
            result = execute_tool(tool_name, args, settings=settings)

            # Логируем для вывода
            tool_calls_log.append(
                {
                    "tool": tool_name,
                    "args": args,
                    "result": result,
                }
            )

            # Добавляем результат в историю сообщений
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result,
                }
            )

    # Достигнут лимит итераций
    print("Достигнут лимит итераций (10)", file=sys.stderr)

    # Пытаемся получить ответ из последнего сообщения assistant
    last_answer = ""
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and msg.get("content"):
            last_answer = msg.get("content", "")
            break

    source = extract_source_from_answer(last_answer, messages)

    return {
        "answer": last_answer or "Достигнут лимит итераций",
        "source": source,
        "tool_calls": tool_calls_log,
    }


def format_response(
    answer: str, source: str, tool_calls: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Форматирует ответ в требуемый JSON формат.

    Args:
        answer: Текст ответа
        source: Источник (путь к файлу)
        tool_calls: Список вызовов инструментов

    Returns:
        Словарь с полями answer, source и tool_calls
    """
    return {
        "answer": answer,
        "source": source,
        "tool_calls": tool_calls,
    }


def load_env_file(env_path: str) -> None:
    """
    Загружает переменные окружения из .env файла для локальной разработки.

    Args:
        env_path: Путь к .env файлу
    """
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip().upper()
            value = value.strip()
            # Удаляем кавычки если есть
            if value and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]
            if key not in os.environ:
                os.environ[key] = value


def main() -> int:
    """
    Главная функция агента.

    Returns:
        Код выхода: 0 при успехе, 1 при ошибке
    """
    try:
        # Загружаем .env файлы для локальной разработки
        # .env.agent.secret — LLM credentials (API key, base, model)
        # .env.docker.secret — LMS API key для query_api аутентификации
        # При работе авточекера переменные будут инжектиться напрямую
        load_env_file(".env.agent.secret")
        load_env_file(".env.docker.secret")

        args = parse_args()
        settings = AgentSettings()

        # Запускаем агентовый цикл
        result = run_agentic_loop(args.question, settings)

        # Форматируем и выводим ответ
        response = format_response(
            answer=result["answer"],
            source=result["source"],
            tool_calls=result["tool_calls"],
        )

        # Только валидный JSON на stdout
        print(json.dumps(response, ensure_ascii=False))

        return 0

    except httpx.HTTPError as e:
        print(f"HTTP ошибка: {e}", file=sys.stderr)
        return 1
    except KeyError as e:
        print(f"Ошибка парсинга ответа API: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Неожиданная ошибка: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
