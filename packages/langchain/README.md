# prefactor-langchain

LangChain integration for Prefactor observability. This package provides automatic tracing for LangChain agents using LangChain-specific span types.

## Installation

```bash
pip install prefactor-langchain
```

## Usage

```python
from prefactor_langchain import PrefactorMiddleware

# Create middleware with your Prefactor API credentials
middleware = PrefactorMiddleware(
    api_url="https://api.prefactor.ai",
    api_token="your-api-token"
)

# Use with LangChain's create_agent()
# Your agent will automatically create spans for:
# - Agent execution (langchain:agent)
# - LLM calls (langchain:llm)
# - Tool executions (langchain:tool)
```

## Span Types

This package creates LangChain-specific spans with the `langchain:*` namespace:

- **`langchain:agent`** - Agent executions and chain runs
- **`langchain:llm`** - LLM calls with model metadata (name, provider, token usage)
- **`langchain:tool`** - Tool executions including retrievers

Each span payload includes:
- Timing information (start_time, end_time)
- Inputs and outputs
- Error information with stack traces
- LangChain-specific metadata

Trace correlation (span_id, parent_span_id, trace_id) is handled automatically by the prefactor-next client.

## Features

- **Automatic LLM call tracing** - Captures model name, provider, token usage, temperature
- **Tool execution tracing** - Records tool name, arguments, execution time
- **Agent/chain tracing** - Tracks agent lifecycle and message history
- **Token usage capture** - Automatically extracts prompt/completion/total tokens
- **Error tracking** - Captures error type, message, and stack traces
- **Automatic parent-child relationships** - Uses SpanContextStack for hierarchy

## Architecture

This package follows the LangChain Adapter Redesign principles:

1. **Package Isolation**: LangChain-specific span types and schemas live in this package
2. **Opaque Payloads**: Span data is sent as payload to prefactor-next
3. **Type Namespacing**: Uses `langchain:agent`, `langchain:llm`, `langchain:tool` prefixes
4. **Uses prefactor-next**: All span/instance management via the prefactor-next client

The middleware:
1. Creates a `PrefactorNextClient` for async queue-based operations
2. Registers an agent instance on first use
3. Creates spans with LangChain-specific payloads
4. Leverages `SpanContextStack` for automatic parent detection

## Development

Run tests:
```bash
pytest tests/
```

## License

MIT
