# Agent Architecture

## Overview

This project implements a **System Agent** — a CLI tool that connects to an LLM (Qwen Code) and uses **tools** to navigate the project's documentation (wiki), read source code, and query the running backend API to provide accurate answers with source references.

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
│  │  (question) │  │ (.env files) │→ │                  │   │
│  └─────────────┘  └──────────────┘  └──────────────────┘   │
│                                              │               │
│                    ┌─────────────────────────┴──────────┐   │
│                    │         Tools                      │   │
│                    │  ┌────────────┐  ┌──────────────┐  │   │
│                    │  │ read_file  │  │ list_files   │  │   │
│                    │  └────────────┘  └──────────────┘  │   │
│                    │  ┌────────────────────────────┐    │   │
│                    │  │ query_api                  │    │   │
│                    │  └────────────────────────────┘    │   │
│                    └────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                                               │
                      ┌────────────────────────┼────────────────┐
                      │                        │                │
                      ▼                        ▼                ▼
┌─────────────────────────────────┐ ┌──────────────────┐ ┌──────────────┐
│     Qwen Code API (on VM)       │ │  Backend API     │ │  File System │
│  http://<vm-ip>:<port>/v1/...   │ │ localhost:42002  │ │  (read-only) │
│     Model: qwen3-coder-plus     │ │ LMS_API_KEY auth │ │              │
└─────────────────────────────────┘ └──────────────────┘ └──────────────┘
```

## Components

### 1. CLI Interface (`argparse`)

- Accepts a single positional argument: the user's question
- Provides help text via `--help`

### 2. Configuration (`pydantic-settings`)

Reads from two `.env` files for local development:

**`.env.agent.secret`** — LLM provider credentials:

| Variable | Description |
|----------|-------------|
| `LLM_API_KEY` | API key for Qwen Code authentication |
| `LLM_API_BASE` | Base URL of the OpenAI-compatible API endpoint |
| `LLM_MODEL` | Model name (default: `qwen3-coder-plus`) |

**`.env.docker.secret`** — Backend API credentials:

| Variable | Description |
|----------|-------------|
| `LMS_API_KEY` | API key for backend authentication (used by `query_api`) |
| `AGENT_API_BASE_URL` | Base URL of the backend API (default: `http://localhost:42002`) |

**Important:** The autochecker injects its own credentials via environment variables, so the agent must read from environment, not hardcode values.

### 3. Tools

The agent has **three tools** for interacting with the file system and backend API:

#### `read_file(path: str)`

Reads the contents of a file from the project repository.

- **Parameters:** `path` — relative path from project root (e.g., `wiki/git-workflow.md`)
- **Returns:** File contents as a string, or an error message
- **Security:** Blocks paths that traverse outside the project directory
- **Use case:** Reading documentation (wiki/), source code (.py files), configuration files (docker-compose.yml, Dockerfile)

#### `list_files(path: str)`

Lists files and directories at a given path.

- **Parameters:** `path` — relative directory path from project root (e.g., `wiki`)
- **Returns:** Newline-separated list of entries
- **Security:** Blocks paths that traverse outside the project directory
- **Use case:** Discovering project structure, finding wiki files, exploring backend routers

#### `query_api(method: str, path: str, body: str | None = None)`

Sends an HTTP request to the backend API.

- **Parameters:**
  - `method` — HTTP method (GET, POST, PUT, DELETE, etc.)
  - `path` — endpoint path (e.g., `/items/`, `/analytics/completion-rate`)
  - `body` — optional JSON request body for POST/PUT requests
- **Returns:** JSON string with `status_code` and `body` fields
- **Authentication:** Uses `LMS_API_KEY` from environment variables (Bearer token)
- **Use case:** Querying live data (item count, scores, analytics), checking status codes, diagnosing API errors

### 4. Agentic Loop

The core reasoning engine that orchestrates tool usage:

```
1. Initialize messages = [system_prompt, user_question]
2. Loop (max 10 iterations):
   a. Send messages + tool schemas to LLM
   b. If LLM returns tool_calls:
      - Execute each tool (read_file, list_files, or query_api)
      - For query_api: pass LMS_API_KEY for authentication
      - Append results as tool role messages
      - Continue loop
   c. If LLM returns text answer (no tool_calls):
      - Extract answer and source
      - Return JSON and exit
3. If max iterations reached, return best available answer
```

### 5. HTTP Client (`httpx`)

Two HTTP clients are used:

**LLM Client:**

- Sends POST requests to `{LLM_API_BASE}/chat/completions`
- Uses Bearer token authentication with `LLM_API_KEY`
- 60-second timeout
- Handles HTTP errors gracefully

**API Client (query_api):**

- Sends requests to `{AGENT_API_BASE_URL}{path}`
- Uses Bearer token authentication with `LMS_API_KEY`
- 30-second timeout
- Handles connection errors, timeouts, and HTTP errors

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
2. **Config Load**: Agent reads `.env.agent.secret` (LLM credentials) and `.env.docker.secret` (backend API key)
3. **Agentic Loop**:
   - Send question + tool schemas to LLM
   - LLM decides which tools to call based on question type:
     - Wiki/documentation questions → `list_files` + `read_file`
     - System facts (framework, ports) → `read_file` for source code
     - Data queries (item count, scores) → `query_api`
     - Bug diagnosis → `query_api` for error, then `read_file` for source code
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

1. **Identify question type** and choose appropriate tools:
   - Wiki/documentation questions → `list_files` + `read_file`
   - System facts (framework, ports) → `read_file` for source code/configs
   - Data queries (item count, scores, status codes) → `query_api`
   - Bug diagnosis → `query_api` for error, then `read_file` for source code
2. **Execute tools iteratively** until enough information is gathered
3. **Include a `source` reference** in the final answer:
   - File path for wiki/code questions (e.g., `wiki/git-workflow.md#section`)
   - `api` for data queries from backend
   - `general` for questions not about the project
4. **Format the answer as JSON** with `answer` and `source` fields

Example prompt:

```
Вы — System Agent, помогающий пользователям находить информацию в проекте.

У вас есть три инструмента:
1. list_files(path) —列出 файлы в директории проекта
2. read_file(path) — прочитать содержимое файла из проекта
3. query_api(method, path, body) — отправить HTTP запрос к backend API

Когда какой инструмент использовать:
- list_files: для навигации по структуре проекта (wiki/, backend/, и т.д.)
- read_file: для чтения документации (wiki/), исходного кода (.py файлы), конфигурации
- query_api: для получения данных из running backend системы:
  - Количество items в базе данных: GET /items/
  - Статус коды ответов: запросы к API без авторизации
  - Analytics данные: /analytics/* endpoints
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
2. Configure `.env.agent.secret` and `.env.docker.secret`:

   ```bash
   # .env.agent.secret — LLM credentials
   LLM_API_KEY=your-api-key
   LLM_API_BASE=http://<vm-ip>:<port>/v1
   LLM_MODEL=qwen3-coder-plus

   # .env.docker.secret — Backend API key
   LMS_API_KEY=my-secret-api-key
   ```

### Usage

```bash
# Basic usage
uv run agent.py "How do you resolve a merge conflict?"

# Query API for data
uv run agent.py "How many items are in the database?"

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
- Tools are called correctly for each question type

## Project Structure

```
se-toolkit-lab-6/
├── agent.py                  # Main CLI agent with agentic loop
├── .env.agent.secret         # LLM configuration (gitignored)
├── .env.docker.secret        # Backend API key (gitignored)
├── AGENT.md                  # This file — architecture documentation
├── plans/
│   ├── task-2.md             # Implementation plan for Documentation Agent
│   └── task-3.md             # Implementation plan for System Agent
├── tests/
│   └── test_agent.py         # Regression tests (5 tests)
├── wiki/
│   ├── qwen.md               # Qwen Code setup instructions
│   └── git-workflow.md       # Example documentation
└── backend/
    └── app/
        ├── main.py           # FastAPI backend entry point
        └── routers/          # API route handlers
```

## Lessons Learned (Task 3)

### Key Insights

1. **Two distinct API keys**: `LLM_API_KEY` (in `.env.agent.secret`) authenticates with the LLM provider, while `LMS_API_KEY` (in `.env.docker.secret`) authenticates with the backend API. Mixing them up causes authentication failures.

2. **Environment variable loading**: The agent must read from both `.env.agent.secret` and `.env.docker.secret` for local development, but the autochecker injects its own values via environment variables. Using `load_env_file()` with fallback to environment ensures both modes work.

3. **Tool description clarity**: The LLM needs clear guidance on when to use each tool. Vague descriptions lead to wrong tool selection (e.g., using `read_file` for data queries).

4. **Error handling in query_api**: The backend might be unavailable during testing. Proper error handling (connection errors, timeouts) prevents crashes and provides useful feedback.

5. **Source extraction**: For API queries, the source should be "api" rather than a file path. The `extract_source_from_answer()` function was updated to handle this.

### Benchmark Results

Initial score: _/10 (to be filled after first run)

First failures:

- [ ] ...

Iteration strategy:

1. Fix tool descriptions if LLM calls wrong tool
2. Fix tool implementation if errors occur
3. Adjust system prompt for clarity

### Final Eval Score

_ /10 (to be updated after passing all tests)
