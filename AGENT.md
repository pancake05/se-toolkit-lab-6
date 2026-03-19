# Agent Architecture

## Overview

This project implements a **Documentation Agent** — a CLI tool that connects to an LLM (Qwen Code) and uses **tools** to navigate the project's documentation (wiki) and provide accurate answers with source references.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      User (CLI)                             │
│              uv run agent.py "Question"                     │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                     agent.py                                │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  argparse   │→ │   Settings   │→ │  Agentic Loop    │   │
│  │  (question) │  │ (.env file)  │  │                  │   │
│  └─────────────┘  └──────────────┘  └──────────────────┘   │
│                                              │               │
│                    ┌─────────────────────────┴──────────┐   │
│                    │         Tools                      │   │
│                    │  ┌────────────┐  ┌──────────────┐  │   │
│                    │  │ read_file  │  │ list_files   │  │   │
│                    │  └────────────┘  └──────────────┘  │   │
│                    └────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                                               │
                                               ▼
┌─────────────────────────────────────────────────────────────┐
│              Qwen Code API (on VM)                          │
│         http://<vm-ip>:<port>/v1/chat/completions           │
│         Model: qwen3-coder-plus                             │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. CLI Interface (`argparse`)

- Accepts a single positional argument: the user's question
- Provides help text via `--help`

### 2. Configuration (`pydantic-settings`)

Reads from `.env.agent.secret`:

| Variable | Description |
|----------|-------------|
| `LLM_API_KEY` | API key for Qwen Code authentication |
| `LLM_API_BASE` | Base URL of the OpenAI-compatible API endpoint |
| `LLM_MODEL` | Model name (default: `qwen3-coder-plus`) |

### 3. Tools

The agent has two tools for interacting with the file system:

#### `read_file(path: str)`

Reads the contents of a file from the project repository.

- **Parameters:** `path` — relative path from project root (e.g., `wiki/git-workflow.md`)
- **Returns:** File contents as a string, or an error message
- **Security:** Blocks paths that traverse outside the project directory

#### `list_files(path: str)`

Lists files and directories at a given path.

- **Parameters:** `path` — relative directory path from project root (e.g., `wiki`)
- **Returns:** Newline-separated list of entries
- **Security:** Blocks paths that traverse outside the project directory

### 4. Agentic Loop

The core reasoning engine that orchestrates tool usage:

```
1. Initialize messages = [system_prompt, user_question]
2. Loop (max 10 iterations):
   a. Send messages + tool schemas to LLM
   b. If LLM returns tool_calls:
      - Execute each tool
      - Append results as tool role messages
      - Continue loop
   c. If LLM returns text answer (no tool_calls):
      - Extract answer and source
      - Return JSON and exit
3. If max iterations reached, return best available answer
```

### 5. HTTP Client (`httpx`)

- Sends POST requests to `{LLM_API_BASE}/chat/completions`
- Uses Bearer token authentication
- 60-second timeout
- Handles HTTP errors gracefully

### 6. Response Formatter

- Extracts answer and source from the agentic loop result
- Outputs JSON with required fields:

  ```json
  {
    "answer": "...",
    "source": "wiki/git-workflow.md#section-anchor",
    "tool_calls": [...]
  }
  ```

## Data Flow

1. **Input**: User provides question as CLI argument
2. **Config Load**: Agent reads `.env.agent.secret`
3. **Agentic Loop**:
   - Send question + tool definitions to LLM
   - LLM decides which tools to call
   - Execute tools, feed results back
   - Repeat until LLM provides final answer
4. **Output**: Print structured JSON to stdout

## Output Format

**stdout** (only valid JSON):

```json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git-workflow.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "..."
    }
  ]
}
```

**stderr** (debug/error messages):

```
Итерация 1/10
Отправка запроса к http://...
Выполнение инструмента: list_files({'path': 'wiki'})
Получен ответ от LLM
```

## Error Handling

| Error Type | Exit Code | Output |
|------------|-----------|--------|
| HTTP error | 1 | Error message to stderr |
| Parse error | 1 | Error message to stderr |
| Success | 0 | JSON to stdout |

## Security

### Path Traversal Protection

Both tools validate paths to prevent accessing files outside the project:

```python
def is_safe_path(path: str) -> tuple[bool, Path]:
    project_root = get_project_root()
    absolute_path = (project_root / path).resolve()
    
    try:
        absolute_path.relative_to(project_root)
        return True, absolute_path
    except ValueError:
        return False, absolute_path
```

This ensures:

- No `../` traversal attacks
- All file access is confined to the project directory
- Symlinks are resolved before validation

## System Prompt Strategy

The system prompt instructs the LLM to:

1. Use `list_files` to discover wiki structure
2. Use `read_file` to read relevant documentation
3. Include a `source` reference in the final answer (file path + section anchor)
4. Format the answer as JSON with `answer` and `source` fields

Example prompt:

```
Вы — Documentation Agent, помогающий пользователям находить информацию в документации проекта.

У вас есть два инструмента:
1. list_files(path) —列出 файлы в директории
2. read_file(path) — прочитать содержимое файла

Порядок работы:
1. Используйте list_files для навигации по структуре проекта
2. Используйте read_file для чтения содержимого файлов
3. Найдите точный раздел, отвечающий на вопрос пользователя
4. В ответе укажите source: путь к файлу и якорь раздела
```

## LLM Provider

- **Provider**: Qwen Code API
- **Deployment**: Self-hosted on VM via [`qwen-code-oai-proxy`](https://github.com/inno-se-toolkit/qwen-code-oai-proxy)
- **Model**: `qwen3-coder-plus` (Qwen 3 Coder Plus)
- **API Compatibility**: OpenAI-compatible (`/v1/chat/completions`)
- **Function Calling**: Supports tool definitions and returns `tool_calls` in response

### Why Qwen Code?

- 1000 free requests per day
- Available in Russia
- No credit card required
- Strong tool-calling capabilities

## How to Run

### Prerequisites

1. Set up Qwen Code API on your VM (see [`wiki/qwen.md`](wiki/qwen.md))
2. Configure `.env.agent.secret`:

   ```bash
   LLM_API_KEY=your-api-key
   LLM_API_BASE=http://<vm-ip>:<port>/v1
   LLM_MODEL=qwen3-coder-plus
   ```

### Usage

```bash
# Basic usage
uv run agent.py "How do you resolve a merge conflict?"

# With help
uv run agent.py --help
```

## Testing

Run the regression tests:

```bash
pytest tests/test_agent.py -v
```

Tests verify:

- `agent.py` runs successfully
- Output is valid JSON
- Required fields (`answer`, `source`, `tool_calls`) are present
- Tools are called correctly for documentation questions

## Project Structure

```
se-toolkit-lab-6/
├── agent.py              # Main CLI agent with agentic loop
├── .env.agent.secret     # LLM configuration (gitignored)
├── AGENT.md              # This file — architecture documentation
├── plans/
│   └── task-2.md         # Implementation plan for Documentation Agent
├── tests/
│   └── test_agent.py     # Regression tests
└── wiki/
    ├── qwen.md           # Qwen Code setup instructions
    └── git-workflow.md   # Example documentation
```

## Future Extensions (Task 3)

- **Backend Integration**: Add `query_api` tool to query the LMS backend
- **Domain Knowledge**: Answer questions about courses, students, grades
- **Multi-hop Reasoning**: Chain multiple tool calls for complex queries
