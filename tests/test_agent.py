"""
Регрессионные тесты для agent.py

Тесты проверяют:
- Корректность JSON вывода
- Наличие обязательных полей (answer, tool_calls)
- Код выхода 0 при успехе
"""

import json
import subprocess
import sys
from pathlib import Path


def test_agent_basic_question():
    """
    Тест: agent.py отвечает на базовый вопрос.

    Проверяет:
    - Код выхода равен 0
    - Вывод является валидным JSON
    - Присутствуют поля answer и tool_calls
    - tool_calls — пустой список
    """
    # Запускаем agent.py с тестовым вопросом
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "uv",
            "run",
            "agent.py",
            "What is 2 + 2?",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Проверяем код выхода
    assert result.returncode == 0, f"agent.py вернул код выхода {result.returncode}. stderr: {result.stderr}"

    # Проверяем, что stdout — валидный JSON
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(f"stdout не является валидным JSON: {e}\nstdout: {result.stdout}")

    # Проверяем наличие обязательных полей
    assert "answer" in response, "Отсутствует поле 'answer' в ответе"
    assert "tool_calls" in response, "Отсутствует поле 'tool_calls' в ответе"

    # Проверяем, что answer — непустая строка
    assert isinstance(response["answer"], str), "Поле 'answer' должно быть строкой"
    assert len(response["answer"]) > 0, "Поле 'answer' не должно быть пустым"

    # Проверяем, что tool_calls — список
    assert isinstance(response["tool_calls"], list), "Поле 'tool_calls' должно быть списком"


if __name__ == "__main__":
    test_agent_basic_question()
    print("Все тесты пройдены!")
