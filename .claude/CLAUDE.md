# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Prefactor SDK provides automatic observability for LangChain agents. It captures traces of LLM calls, tool executions, and agent workflows with zero code changes via two integration methods:

1. **Middleware API (Recommended)**: For LangChain 1.0+ using `create_agent()`
2. **Callback Handler API (Legacy)**: For older codebases using manual callback passing

## Development Environment

This project uses **mise** for reproducible development environments. On first setup:

    $ mise install
    $ mise run setup

The environment automatically:
- Sets up Python 3.13 with a virtual environment (`.venv`)
- Installs dependencies via `uv sync` (automatically on directory entry via hooks)
- Configures git pre-commit hooks via lefthook

Available mise tasks:

    $ mise run test       # Run pytest
    $ mise run lint       # Run ruff check --fix
    $ mise run format     # Run ruff format
    $ mise run typecheck  # Run ty type checker
    $ mise run check      # Run all quality checks

## Essential Commands

### Testing

    # Run all tests
    pytest

    # Run specific test file
    pytest tests/test_config.py

    # Run specific test function
    pytest tests/test_config.py::test_config_defaults -v

    # Run with verbose output
    pytest -v

    # Run integration tests only
    pytest tests/integration/

### Code Quality

**Important**: Most quality checks run automatically via Claude Code hooks (configured in `.claude/settings.json`). You typically don't need to run these manually.

    # Format code (auto-runs after Edit/Write on .py files)
    ruff format .

    # Lint and auto-fix (auto-runs after Edit/Write on .py files)
    ruff check --fix .

    # Type check (auto-runs before git commits)
    uvx ty check .

    # Run all checks manually
    ruff format . && ruff check --fix . && uvx ty check .

## Architecture

### Core Components

**Tracing Layer** (`src/prefactor_sdk/tracing/`):
- `Span`: Data model representing a unit of work (LLM call, tool execution, etc.)
  - Contains: span_id, parent_span_id, trace_id, name, type, timing, inputs/outputs, token usage, errors
  - Span types: AGENT, LLM, TOOL, CHAIN, RETRIEVER
- `Tracer`: Manages span lifecycle (start_span, end_span) and delegates to Transport
- `context.py`: Thread-local context management for tracking active spans and trace IDs

**Transport Layer** (`src/prefactor_sdk/transport/`):
- `Transport` (abstract): Base class defining emit() and close() interface
- `StdioTransport`: Writes spans to stdout as JSON (default, zero-config)
- `HttpTransport`: Async HTTP transport with retry logic for production use

**Instrumentation** (`src/prefactor_sdk/instrumentation/langchain/`):
- `PrefactorMiddleware`: Modern middleware for `create_agent()` (LangChain 1.0+)
  - Implements middleware protocol, wraps model calls
  - Automatically captures inputs, outputs, token usage, and errors
- `PrefactorCallbackHandler`: Legacy callback handler extending `BaseCallbackHandler`
  - Hooks into LangChain events: on_llm_start, on_llm_end, on_tool_start, etc.
  - Maintains span stack for parent-child relationships
- `metadata_extractor.py`: Extracts structured metadata from LangChain runs (model names, token counts, etc.)

**Configuration** (`src/prefactor_sdk/config.py`):
- `Config`: Main configuration with env variable fallbacks
- `HttpTransportConfig`: HTTP-specific settings (URL, token, retries, timeouts)

### Data Flow

1. User calls `prefactor_sdk.init()` or `prefactor_sdk.init_callback()`
2. SDK creates global `Tracer` instance with configured `Transport`
3. SDK returns `PrefactorMiddleware` or `PrefactorCallbackHandler`
4. User passes middleware/handler to LangChain components
5. During execution:
   - Middleware/handler intercepts LangChain events
   - Calls `tracer.start_span()` to create span with inputs
   - Tracks execution in thread-local context
   - Calls `tracer.end_span()` with outputs/errors
   - Tracer calls `transport.emit(span)` to send span data
6. Transport serializes span to JSON and sends to destination (stdout or HTTP)

### Key Design Patterns

- **Global Singleton Pattern**: Single tracer/middleware instance shared across the application (`_global_tracer`, `_global_middleware`)
- **Context Manager Pattern**: Thread-local storage for tracking active spans and maintaining parent-child relationships
- **Strategy Pattern**: Pluggable transport layer (stdio vs HTTP)
- **Decorator/Middleware Pattern**: Wraps LangChain operations for transparent instrumentation

## Testing Structure

Tests mirror source structure:
- `tests/tracing/` - Core tracing functionality
- `tests/transport/` - Transport implementations
- `tests/instrumentation/` - LangChain integration
- `tests/integration/` - End-to-end tests with real LangChain components
- `tests/utils/` - Utility functions

Use `pytest-asyncio` for async tests. Mock HTTP with `aioresponses`.

## Environment Variables

Transport selection:
- `PREFACTOR_TRANSPORT`: "stdio" (default) or "http"

HTTP transport (when using HTTP):
- `PREFACTOR_API_URL`: API endpoint (required for HTTP)
- `PREFACTOR_API_TOKEN`: Authentication token (required for HTTP)
- `PREFACTOR_AGENT_ID`: Agent identifier (optional)
- `PREFACTOR_AGENT_VERSION`: Agent version (optional)

Capture settings:
- `PREFACTOR_SAMPLE_RATE`: 0.0-1.0 (default: 1.0)
- `PREFACTOR_CAPTURE_INPUTS`: true/false (default: true)
- `PREFACTOR_CAPTURE_OUTPUTS`: true/false (default: true)
- `PREFACTOR_MAX_INPUT_LENGTH`: bytes (default: 10000)
- `PREFACTOR_MAX_OUTPUT_LENGTH`: bytes (default: 10000)

## Common Patterns

### Adding New Span Types
1. Add enum value to `SpanType` in `src/prefactor_sdk/tracing/span.py`
2. Update instrumentation to create spans with new type
3. Add tests verifying span creation and metadata

### Adding New Transport
1. Create new file in `src/prefactor_sdk/transport/`
2. Implement `Transport` abstract base class (emit, close)
3. Update `init()` in `src/prefactor_sdk/__init__.py` to instantiate new transport
4. Add tests in `tests/transport/`

### Extending Metadata Extraction
1. Update `extract_metadata()` in `instrumentation/langchain/metadata_extractor.py`
2. Handle new LangChain run types or extract additional fields
3. Add tests in `tests/instrumentation/test_metadata_extractor.py`
