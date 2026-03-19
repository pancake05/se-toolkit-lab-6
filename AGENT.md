# Agent Architecture

## Overview

This project implements a CLI agent that connects to an LLM (Qwen Code) and returns structured JSON answers. The agent serves as the foundation for more advanced features (tools, agentic loop) in subsequent tasks.

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
│  │  argparse   │→ │   Settings   │→ │   HTTP Client    │   │
│  │  (question) │  │ (.env file)  │  │   (httpx)        │   │
│  └─────────────┘  └──────────────┘  └──────────────────┘   │
│                                              │               │
└──────────────────────────────────────────────┼───────────────┘
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

### 3. HTTP Client (`httpx`)

- Sends POST request to `{LLM_API_BASE}/chat/completions`
- Uses Bearer token authentication
- 60-second timeout
- Handles HTTP errors gracefully

### 4. Response Formatter

- Extracts answer from API response: `choices[0].message.content`
- Outputs JSON with required fields:
  ```json
  {"answer": "...", "tool_calls": []}
  ```

## Data Flow

1. **Input**: User provides question as CLI argument
2. **Config Load**: Agent reads `.env.agent.secret`
3. **API Call**: HTTP POST to LLM endpoint
4. **Parse**: Extract answer from JSON response
5. **Output**: Print structured JSON to stdout

## Output Format

**stdout** (only valid JSON):
```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```

**stderr** (debug/error messages):
```
Отправка запроса к http://...
Получен ответ от LLM
```

## Error Handling

| Error Type | Exit Code | Output |
|------------|-----------|--------|
| HTTP error | 1 | Error message to stderr |
| Parse error | 1 | Error message to stderr |
| Success | 0 | JSON to stdout |

## LLM Provider

- **Provider**: Qwen Code API
- **Deployment**: Self-hosted on VM via [`qwen-code-oai-proxy`](https://github.com/inno-se-toolkit/qwen-code-oai-proxy)
- **Model**: `qwen3-coder-plus` (Qwen 3 Coder Plus)
- **API Compatibility**: OpenAI-compatible (`/v1/chat/completions`)

### Why Qwen Code?

- 1000 free requests per day
- Available in Russia
- No credit card required
- Strong tool-calling capabilities (for future tasks)

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
uv run agent.py "What does REST stand for?"

# With help
uv run agent.py --help
```

## Testing

Run the regression test:

```bash
pytest tests/test_agent.py -v
```

The test verifies:
- `agent.py` runs successfully
- Output is valid JSON
- Required fields (`answer`, `tool_calls`) are present

## Project Structure

```
se-toolkit-lab-6/
├── agent.py              # Main CLI agent
├── .env.agent.secret     # LLM configuration (gitignored)
├── AGENT.md              # This file — architecture documentation
├── plans/
│   └── task-1.md         # Implementation plan
├── tests/
│   └── test_agent.py     # Regression tests
└── wiki/
    └── qwen.md           # Qwen Code setup instructions
```

## Future Extensions (Tasks 2–3)

- **Tools**: Add `tool_calls` array with actual tool invocations
- **Agentic Loop**: Multi-turn reasoning with tool usage
- **Domain Knowledge**: Integration with backend LMS via `query_api` tool
