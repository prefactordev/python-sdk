# Prefactor SDK

Automatic observability for LangChain agents. Trace LLM calls, tool executions, and agent workflows with zero code changes.

## Installation

```bash
pip install prefactor-langchain
```

## Quick Start

```python
import ast
import asyncio
import operator
from langchain.agents import create_agent
from langchain_core.tools import tool
from prefactor_langchain import PrefactorMiddleware

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv}

def _safe_eval(node):
    if isinstance(node, ast.Constant): return node.n
    if isinstance(node, ast.BinOp): return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub): return -_safe_eval(node.operand)
    raise ValueError(f"Unsupported: {node}")

@tool
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression safely."""
    try:
        return str(_safe_eval(ast.parse(expression, mode='eval').body))
    except Exception as e:
        return f"Error: {e}"

async def main():
    middleware = PrefactorMiddleware.from_config(
        api_url="https://api.prefactor.ai",
        api_token="your-token",
        agent_id="my-agent",
        agent_name="My Agent",
    )

    agent = create_agent(
        model="claude-haiku-4-5-20251001",
        tools=[calculator],
        middleware=[middleware],
    )

    # All LLM calls and tool executions are automatically traced
    try:
        result = await agent.ainvoke({"messages": [{"role": "user", "content": "What is 6 * 7?"}]})
    finally:
        await middleware.close()

asyncio.run(main())
```

## Features

- Automatic tracing of LLM calls with token usage
- Tool execution tracking
- Agent workflow visualization
- Parent-child span relationships
- Error tracking and debugging
- Zero-overhead instrumentation

## Development Setup

This project uses [mise](https://mise.jdx.dev) for reproducible development environments with the following tools:

- **Python 3.11** with **uv** as the package manager
- **ty** for blazing-fast type checking (10-100x faster than mypy/pyright)
- **ruff** for linting and formatting (replaces Black, isort, Flake8, etc.)
- **lefthook** for git pre-commit hooks

### Prerequisites

Install mise using one of these methods:

```bash
# macOS (Homebrew)
brew install mise

# Linux/macOS (curl)
curl https://mise.run | sh

# Other methods: https://mise.jdx.dev/getting-started.html
```

After installation, activate mise in your shell:

```bash
# For bash (add to ~/.bashrc)
eval "$(mise activate bash)"

# For zsh (add to ~/.zshrc)
eval "$(mise activate zsh)"

# For fish (add to ~/.config/fish/config.fish)
mise activate fish | source
```

Alternatively, if you use [direnv](https://direnv.net/), mise will activate automatically when you enter the project directory.

### Getting Started

1. Clone the repository:
   ```bash
   git clone https://github.com/prefactordev/python-sdk.git
   cd python-sdk
   ```

2. Install project tools (Python, uv, ruff, etc.):
   ```bash
   mise install
   ```

3. Set up the project (install dependencies and git hooks):
   ```bash
   mise run setup
   ```

   This will:
   - Create a virtual environment at `.venv`
   - Install all dependencies via `uv sync --all-extras`
   - Install git pre-commit hooks via lefthook

4. You're ready to develop! The virtual environment activates automatically when you enter the directory.

### Common Tasks

```bash
# Run tests
mise run test

# Run all quality checks (format, lint, typecheck)
mise run check

# Individual checks
mise run format     # Format code with ruff
mise run lint       # Lint code with ruff
mise run typecheck  # Type check with ty

# Install/update dependencies
mise run install
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest packages/core/tests/test_client.py

# Run with verbose output
pytest -v

# Run specific test
pytest packages/core/tests/test_client.py::TestClient::test_initialize -v
```

### Pre-commit Hooks

Git pre-commit hooks run automatically on each commit via lefthook:

1. `ruff format` - Format staged Python files
2. `ruff check --fix` - Lint and auto-fix staged Python files
3. `uvx ty check` - Type check the entire codebase

To run hooks manually:
```bash
lefthook run pre-commit
```

### Versioning

Package versions are defined in each package's `src/<package>/_version.py` file.
That file is the single source of truth for both runtime `__version__` and build
metadata.

- `packages/http/src/prefactor_http/_version.py`
- `packages/core/src/prefactor_core/_version.py`
- `packages/langchain/src/prefactor_langchain/_version.py`
- `packages/livekit/src/prefactor_livekit/_version.py`

Each package `pyproject.toml` uses Hatch dynamic versioning and reads the version
directly from that `_version.py` file. We do not resolve versions from installed
metadata or parse `pyproject.toml` at import time.

When bumping a package version:

1. Update `__version__` in that package's `_version.py`.
2. Update any dependent package constraints if the new version requires it.
3. Run `mise run test` before committing.

### Project Structure

```text
python-sdk/
├── packages/
│   ├── core/           # Core tracing and span lifecycle
│   ├── http/           # HTTP client for the Prefactor API
│   ├── langchain/      # LangChain instrumentation
│   └── livekit/        # LiveKit instrumentation
├── mise.toml           # mise configuration
├── lefthook.yml        # Git hooks configuration
└── pyproject.toml      # Python project configuration (workspace root)
```

### Tools Reference

| Tool | Purpose | Documentation |
|------|---------|---------------|
| [mise](https://mise.jdx.dev) | Tool version manager | Manages Python, uv, ruff, etc. |
| [uv](https://github.com/astral-sh/uv) | Python package manager | Fast dependency resolution |
| [ruff](https://github.com/astral-sh/ruff) | Linter and formatter | Replaces Black, isort, Flake8 |
| [ty](https://github.com/astral-sh/ty) | Type checker | 10-100x faster than mypy |
| [lefthook](https://github.com/evilmartians/lefthook) | Git hooks manager | Runs pre-commit checks |

### Claude Code Integration

If you use [Claude Code](https://claude.ai/code), hooks are configured in `.claude/settings.json`:

- **PostToolUse**: Automatically formats and lints Python files after editing
- **PreToolUse**: Runs type checking before git commits
