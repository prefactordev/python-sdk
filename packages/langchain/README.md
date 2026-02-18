# prefactor-langchain

LangChain integration for Prefactor observability. This package provides automatic tracing for LangChain agents using LangChain-specific span types.

## Installation

```bash
pip install prefactor-langchain
```

## Usage

### Factory pattern (quickest setup)

```python
from prefactor_langchain import PrefactorMiddleware

middleware = PrefactorMiddleware.from_config(
    api_url="https://api.prefactor.ai",
    api_token="your-api-token",
    agent_id="my-agent",
    agent_name="My Agent",  # optional
)

# Use with LangChain's create_agent()
# Your agent will automatically create spans for:
# - Agent execution (langchain:agent)
# - LLM calls (langchain:llm)
# - Tool executions (langchain:tool)

result = agent.invoke({"messages": [...]})

# Middleware owns both client and instance; close when done
await middleware.close()
```

### Pre-configured client

Pass a client you created yourself when you need full control over its
configuration or when you want to share a client across multiple middlewares.

```python
from prefactor_core import PrefactorCoreClient, PrefactorCoreConfig
from prefactor_http.config import HttpClientConfig
from prefactor_langchain import PrefactorMiddleware

http_config = HttpClientConfig(api_url="https://api.prefactor.ai", api_token="your-api-token")
config = PrefactorCoreConfig(http_config=http_config)
client = PrefactorCoreClient(config)
await client.initialize()

middleware = PrefactorMiddleware(
    client=client,
    agent_id="my-agent",
    agent_name="My Agent",
)

result = agent.invoke({"messages": [...]})

# You own the client; close both separately
await middleware.close()  # closes the agent instance only
await client.close()
```

### Pre-configured instance (spans outside the agent)

Pass an `AgentInstanceHandle` you created yourself when you also need to
instrument code that lives **outside** the LangChain agent — for example,
pre-processing steps, post-processing, or any custom business logic that
should appear as siblings of the agent spans in the same trace.

```python
from prefactor_core import PrefactorCoreClient, PrefactorCoreConfig
from prefactor_http.config import HttpClientConfig
from prefactor_langchain import PrefactorMiddleware

http_config = HttpClientConfig(api_url="https://api.prefactor.ai", api_token="your-api-token")
config = PrefactorCoreConfig(http_config=http_config)
client = PrefactorCoreClient(config)
await client.initialize()

instance = await client.create_agent_instance(agent_id="my-agent")
await instance.start()

# Share the instance with the middleware
middleware = PrefactorMiddleware(instance=instance)

# Instrument your own code using the same instance
async with instance.span("custom:preprocessing") as ctx:
    ctx.set_payload({"step": "preprocess", "status": "ok"})

# Run your agent — the middleware traces it automatically under the same instance
result = agent.invoke({"messages": [...]})

async with instance.span("custom:postprocessing") as ctx:
    ctx.set_payload({"step": "postprocess", "result": str(result)})

# You own the instance and client; clean them up yourself
await instance.finish()
await client.close()
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

Trace correlation (span_id, parent_span_id, trace_id) is handled automatically by the prefactor-core client.

## Features

- **Automatic LLM call tracing** - Captures model name, provider, token usage, temperature
- **Tool execution tracing** - Records tool name, arguments, execution time
- **Agent/chain tracing** - Tracks agent lifecycle and message history
- **Token usage capture** - Automatically extracts prompt/completion/total tokens
- **Error tracking** - Captures error type, message, and stack traces
- **Automatic parent-child relationships** - Uses SpanContextStack for hierarchy
- **Bring your own instance** - Share a single `AgentInstanceHandle` between the middleware and your own instrumentation

## Architecture

This package follows the LangChain Adapter Redesign principles:

1. **Package Isolation**: LangChain-specific span types and schemas live in this package
2. **Opaque Payloads**: Span data is sent as payload to prefactor-core
3. **Type Namespacing**: Uses `langchain:agent`, `langchain:llm`, `langchain:tool` prefixes
4. **Uses prefactor-core**: All span/instance management via the prefactor-core client

The middleware:
1. Accepts a `PrefactorCoreClient`, or a pre-created `AgentInstanceHandle`, or creates its own client via `from_config()`
2. Registers or borrows an agent instance
3. Creates spans with LangChain-specific payloads
4. Leverages `SpanContextStack` for automatic parent detection

## Development

Run tests:
```bash
pytest tests/
```

## License

MIT
