# Prefactor SDK

Automatic observability for LangChain agents. Trace LLM calls, tool executions, and agent workflows with zero code changes.

## Installation

```bash
pip install prefactor-sdk
```

## Quick Start

```python
import prefactor_sdk
from langchain.agents import create_agent

# Initialize Prefactor
middleware = prefactor_sdk.init()

# Create agent with middleware
agent = create_agent(
    model="claude-sonnet-4-5-20250929",
    tools=[...],
    middleware=[middleware]
)

# All operations are automatically traced
result = agent.invoke({"messages": [{"role": "user", "content": "Hello!"}]})
```

## Features

- ✅ Automatic tracing of LLM calls with token usage
- ✅ Tool execution tracking
- ✅ Agent workflow visualization
- ✅ Parent-child span relationships
- ✅ Error tracking and debugging
- ✅ Zero-overhead instrumentation

## Python Development Setup

This project uses modern Python tooling for maximum developer productivity:

- **Python 3.12** with **uv** as the package manager
- **ty** for blazing-fast type checking (10-100x faster than mypy/pyright)
- **ruff** for linting and formatting (replaces Black, isort, Flake8, etc.)
- **devenv** for reproducible development environments
- **Claude Code hooks** (managed via devenv.nix)

### Getting Started

1. Enter the development shell:
   ```bash
   devenv shell
   ```

2. The environment will automatically:
   - Set up Python (using system default, currently 3.13)
   - Create a virtual environment (venv)
   - Install dependencies via `uv sync`
   - Configure git pre-commit hooks (when git is initialized)
   - Generate `.mcp.json` for Claude Code integration

3. Dependencies are automatically installed on shell entry via `uv sync`. The dev dependencies include ty and ruff for type checking and linting.

### Quality Checks

#### Automatic (via Claude Code hooks)
- Python files are automatically formatted with `ruff format` after editing
- Files are automatically linted with `ruff check --fix` after editing
- Type checking runs automatically before git commits

**How it works**: Hooks are configured in `devenv.nix` under `claude.code.hooks`. Devenv automatically generates the `.mcp.json` configuration file that Claude Code reads.

#### Manual
```bash
# Format code
ruff format .

# Lint and fix issues
ruff check --fix .

# Type check
uvx ty check .

# Run all checks
ruff format . && ruff check --fix . && uvx ty check .
```

### Pre-commit Hooks

Git pre-commit hooks are automatically configured via devenv. They run:
1. `ruff format` - Format Python code
2. `ruff check --fix` - Lint and auto-fix issues
3. `uvx ty check` - Type check the codebase

### Tools Overview

- **uv**: Fast Python package manager (https://github.com/astral-sh/uv)
- **ty**: Fast Python type checker (https://github.com/astral-sh/ty)
- **ruff**: Fast Python linter and formatter (https://github.com/astral-sh/ruff)
- **devenv**: Declarative dev environments with Claude Code integration (https://devenv.sh)

### Hook Configuration

All hooks are defined in `devenv.nix` under `claude.code.hooks`:
- **PostToolUse**: Runs after Edit/Write operations on .py files
- **PreToolUse**: Runs before Bash commands containing "git commit"

This configuration is automatically synced to `.mcp.json` by devenv, eliminating the need for manual `.claude/settings.local.json` management.
