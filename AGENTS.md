# Agents Guide for Prefactor Python SDK

## Build/Test Commands
- **Run all tests**: `mise run test`
- **Run single test**: `mise run test packages/http/tests/test_client.py::TestClient::test_method -v`
- **Run package tests**: `mise run test packages/http/tests/ -v`
- **Lint**: `mise run lint`
- **Format**: `mise run format`
- **Type check**: `mise run typecheck`
- **Run all quality checks**: `mise run check` (runs format, lint, typecheck)

## Mise
- Mise manages Python 3.11, uv, ruff, jq, and lefthook
- Auto-installs dependencies on directory enter via hook
- **Setup project**: `mise run setup` (installs deps and lefthook)
- **Install dependencies**: `mise run install` (runs `uv sync --all-extras`)

## Code Style
- Python 3.11+ with `from __future__ import annotations`
- Line length: 88 chars, double quotes, spaces for indent
- Import order: stdlib → third-party → local (ruff handles this)
- Use `| None` instead of `Optional`, `list[T]` instead of `List[T]`
- Naming: `snake_case` for vars/functions, `PascalCase` for classes, `UPPER_CASE` for constants
- Exception classes in `exceptions.py`, prefix with module name (e.g., `PrefactorHttpError`)
- All public functions/classes need docstrings (Google style)
- Use `async/await` for async code; use `TYPE_CHECKING` for type-only imports

## Monorepo Structure
- 4 packages in `packages/`: core, http, langchain, livekit
- Each package has own `pyproject.toml`
- Tests live in `packages/<name>/tests/`
