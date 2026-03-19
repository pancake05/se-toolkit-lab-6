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
    """

    llm_api_key: str
    llm_api_base: str
    llm_model: str

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


# Словарь доступных инструментов
TOOLS = {
    "read_file": read_file,
    "list_files": list_files,
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
    ]


def get_system_prompt() -> str:
    """
    Возвращает системный промпт для агента.

    Returns:
        Текст системного промпта
    """
    return """Вы — Documentation Agent, помогающий пользователям находить информацию в документации проекта.

У вас есть два инструмента:
1. list_files(path) —列出 файлы в директории
2. read_file(path) — прочитать содержимое файла

Порядок работы:
1. Используйте list_files для навигации по структуре проекта (особенно директория wiki/)
2. Используйте read_file для чтения содержимого файлов
3. Найдите точный раздел, отвечающий на вопрос пользователя
4. В ответе укажите:
   - answer: краткий ответ на вопрос
   - source: путь к файлу и якорь раздела (например, wiki/git-workflow.md#resolving-merge-conflicts)

Если вопрос не связан с документацией проекта, ответьте своими знаниями и укажите source: "general".

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


def execute_tool(tool_name: str, args: dict[str, Any]) -> str:
    """
    Выполняет инструмент по имени.

    Args:
        tool_name: Имя инструмента
        args: Аргументы для инструмента

    Returns:
        Результат выполнения инструмента
    """
    if tool_name not in TOOLS:
        return f"Ошибка: неизвестный инструмент '{tool_name}'"

    func = TOOLS[tool_name]
    try:
        # Вызываем функцию с аргументами
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
            result = execute_tool(tool_name, args)

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
        # Загружаем .env.agent.secret для локальной разработки
        # При работе авточекера переменные будут инжектиться напрямую
        load_env_file(".env.agent.secret")

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
