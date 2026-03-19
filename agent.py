#!/usr/bin/env python3
"""
Agent CLI — отправляет вопрос в LLM и возвращает структурированный JSON ответ.

Использование:
    uv run agent.py "Ваш вопрос здесь"

Выход:
    JSON на stdout: {"answer": "...", "tool_calls": []}
    Все отладочные сообщения — в stderr
"""

import argparse
import json
import sys
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


def call_llm(question: str, settings: AgentSettings) -> str:
    """
    Отправляет вопрос в LLM и возвращает ответ.

    Args:
        question: Текст вопроса
        settings: Настройки API

    Returns:
        Текст ответа от LLM

    Raises:
        httpx.HTTPError: При ошибке HTTP запроса
        KeyError: При неверной структуре ответа API
    """
    url = f"{settings.llm_api_base}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": question}],
    }

    print(f"Отправка запроса к {url}...", file=sys.stderr)

    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()

    data = response.json()
    answer = data["choices"][0]["message"]["content"]

    print(f"Получен ответ от LLM", file=sys.stderr)

    return answer


def format_response(answer: str) -> dict[str, Any]:
    """
    Форматирует ответ в требуемый JSON формат.

    Args:
        answer: Текст ответа от LLM

    Returns:
        Словарь с полями answer и tool_calls
    """
    return {
        "answer": answer,
        "tool_calls": [],
    }


def load_env_file(env_path: str) -> None:
    """
    Загружает переменные окружения из .env файла для локальной разработки.

    Args:
        env_path: Путь к .env файлу
    """
    import os

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

        answer = call_llm(args.question, settings)
        response = format_response(answer)

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
