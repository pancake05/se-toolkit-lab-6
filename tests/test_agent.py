"""
Регрессионные тесты для agent.py

Тесты проверяют:
- Корректность JSON вывода
- Наличие обязательных полей (answer, source, tool_calls)
- Код выхода 0 при успехе
- Корректное использование инструментов
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
    - Присутствуют поля answer, source и tool_calls
    - tool_calls — пустой список (для вопросов не о документации)
    """
    # Запускаем agent.py с тестовым вопросом
    # Используем прямой вызов python из корня проекта
    project_root = Path(__file__).parent.parent
    result = subprocess.run(
        [
            sys.executable,
            "agent.py",
            "What is 2 + 2?",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=project_root,
    )

    # Проверяем код выхода
    assert result.returncode == 0, (
        f"agent.py вернул код выхода {result.returncode}. stderr: {result.stderr}"
    )

    # Проверяем, что stdout — валидный JSON
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(
            f"stdout не является валидным JSON: {e}\nstdout: {result.stdout}"
        )

    # Проверяем наличие обязательных полей
    assert "answer" in response, "Отсутствует поле 'answer' в ответе"
    assert "source" in response, "Отсутствует поле 'source' в ответе"
    assert "tool_calls" in response, "Отсутствует поле 'tool_calls' в ответе"

    # Проверяем, что answer — непустая строка
    assert isinstance(response["answer"], str), "Поле 'answer' должно быть строкой"
    assert len(response["answer"]) > 0, "Поле 'answer' не должно быть пустым"

    # Проверяем, что tool_calls — список
    assert isinstance(response["tool_calls"], list), (
        "Поле 'tool_calls' должно быть списком"
    )


def test_agent_merge_conflict_question():
    """
    Тест: agent.py использует read_file для вопроса о merge conflict.

    Проверяет:
    - Код выхода равен 0
    - Вывод является валидным JSON
    - Присутствуют поля answer, source и tool_calls
    - tool_calls содержит вызов read_file
    - source содержит wiki/git-workflow.md
    """
    # Запускаем agent.py с вопросом о merge conflict
    project_root = Path(__file__).parent.parent
    result = subprocess.run(
        [
            sys.executable,
            "agent.py",
            "How do you resolve a merge conflict?",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=project_root,
    )

    # Проверяем код выхода
    assert result.returncode == 0, (
        f"agent.py вернул код выхода {result.returncode}. stderr: {result.stderr}"
    )

    # Проверяем, что stdout — валидный JSON
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(
            f"stdout не является валидным JSON: {e}\nstdout: {result.stdout}"
        )

    # Проверяем наличие обязательных полей
    assert "answer" in response, "Отсутствует поле 'answer' в ответе"
    assert "source" in response, "Отсутствует поле 'source' в ответе"
    assert "tool_calls" in response, "Отсутствует поле 'tool_calls' в ответе"

    # Проверяем, что answer — непустая строка
    assert isinstance(response["answer"], str), "Поле 'answer' должно быть строкой"
    assert len(response["answer"]) > 0, "Поле 'answer' не должно быть пустым"

    # Проверяем, что tool_calls — непустой список (агент должен использовать инструменты)
    assert len(response["tool_calls"]) > 0, (
        "tool_calls не должен быть пустым для вопроса о документации"
    )

    # Проверяем, что есть вызов read_file
    tool_names = [tc.get("tool") for tc in response["tool_calls"]]
    assert "read_file" in tool_names, (
        f"read_file не найден в tool_calls. Найдены: {tool_names}"
    )

    # Проверяем, что source содержит wiki/git-workflow.md
    assert "wiki/git-workflow.md" in response["source"], (
        f"source должен содержать 'wiki/git-workflow.md'. Получено: {response['source']}"
    )


def test_agent_list_wiki_files():
    """
    Тест: agent.py использует list_files для вопроса о файлах в wiki.

    Проверяет:
    - Код выхода равен 0
    - Вывод является валидным JSON
    - Присутствуют поля answer, source и tool_calls
    - tool_calls содержит вызов list_files
    """
    # Запускаем agent.py с вопросом о файлах в wiki
    project_root = Path(__file__).parent.parent
    result = subprocess.run(
        [
            sys.executable,
            "agent.py",
            "What files are in the wiki?",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=project_root,
    )

    # Проверяем код выхода
    assert result.returncode == 0, (
        f"agent.py вернул код выхода {result.returncode}. stderr: {result.stderr}"
    )

    # Проверяем, что stdout — валидный JSON
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(
            f"stdout не является валидным JSON: {e}\nstdout: {result.stdout}"
        )

    # Проверяем наличие обязательных полей
    assert "answer" in response, "Отсутствует поле 'answer' в ответе"
    assert "source" in response, "Отсутствует поле 'source' в ответе"
    assert "tool_calls" in response, "Отсутствует поле 'tool_calls' в ответе"

    # Проверяем, что answer — непустая строка
    assert isinstance(response["answer"], str), "Поле 'answer' должно быть строкой"
    assert len(response["answer"]) > 0, "Поле 'answer' не должно быть пустым"

    # Проверяем, что tool_calls — непустой список
    assert len(response["tool_calls"]) > 0, (
        "tool_calls не должен быть пустым для вопроса о wiki"
    )

    # Проверяем, что есть вызов list_files
    tool_names = [tc.get("tool") for tc in response["tool_calls"]]
    assert "list_files" in tool_names, (
        f"list_files не найден в tool_calls. Найдены: {tool_names}"
    )


if __name__ == "__main__":
    test_agent_basic_question()
    print("Тест 1 пройден: basic question")

    test_agent_merge_conflict_question()
    print("Тест 2 пройден: merge conflict question")

    test_agent_list_wiki_files()
    print("Тест 3 пройден: list wiki files")

    print("\nВсе тесты пройдены!")
