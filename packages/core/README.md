# Prefactor Core

High-level Prefactor SDK with async queue-based processing.

## Features

- **Queue-Based Processing**: Operations are queued and processed asynchronously by a worker pool
- **Non-Blocking API**: Agent execution is never blocked by observability calls
- **Automatic Parent Detection**: Nested spans automatically detect their parent from the context stack
- **Schema Registry**: Compose and register span schemas before instance creation
- **Configurable Workers**: Tune concurrency and retry behavior for the background queue

## Installation

```bash
pip install prefactor-core
```

## Quick Start

```python
import asyncio
from prefactor_core import PrefactorCoreClient, PrefactorCoreConfig
from prefactor_http import HttpClientConfig

async def main():
    config = PrefactorCoreConfig(
        http_config=HttpClientConfig(
            api_url="https://api.prefactor.ai",
            api_token="your-token",
        ),
    )

    async with PrefactorCoreClient(config) as client:
        instance = await client.create_agent_instance(
            agent_id="my-agent",
            agent_version={"name": "My Agent", "external_identifier": "v1.0.0"},
            agent_schema_version={
                "external_identifier": "v1.0.0",
                "span_type_schemas": [
                    {
                        "name": "agent:llm",
                        "title": "LLM Call",
                        "description": "A call to a language model",
                        "params_schema": {
                            "type": "object",
                            "properties": {
                                "model": {"type": "string"},
                                "prompt": {"type": "string"},
                            },
                            "required": ["model", "prompt"],
                        },
                        "result_schema": {
                            "type": "object",
                            "properties": {"response": {"type": "string"}},
                        },
                        "template": "{{model}}: {{prompt}} → {{response}}",
                    },
                ],
            },
        )

        await instance.start()

        async with instance.span("agent:llm") as span:
            span.set_payload({"model": "gpt-4", "prompt": "Hello"})
            result = await call_llm()
            span.set_payload({"model": "gpt-4", "prompt": "Hello", "response": result})

        await instance.finish()

asyncio.run(main())
```

## API Reference

### `PrefactorCoreClient`

The main entry point. Use as an async context manager or call `initialize()` / `close()` manually.

```python
client = PrefactorCoreClient(config)
await client.initialize()
# ... use client ...
await client.close()
```

#### `create_agent_instance`

```python
handle = await client.create_agent_instance(
    agent_id="my-agent",
    agent_version={"name": "My Agent", "external_identifier": "v1.0.0"},
    agent_schema_version=None,        # Optional: auto-generated if schema_registry is configured
    instance_id=None,                 # Optional: pre-assign an ID
    external_schema_version_id=None,  # Optional: reference an existing schema version
) -> AgentInstanceHandle
```

#### `span` (context manager)

```python
async with client.span(
    instance_id="instance_123",
    schema_name="llm",
    parent_span_id=None,  # Optional: auto-detected from context stack if omitted
    span_id=None,         # Optional: pre-assign an ID
) as span:
    span.set_payload({"key": "value"})
```

### `AgentInstanceHandle`

Returned by `create_agent_instance`. Manages the lifecycle of a single agent instance.

```python
handle.id  # -> str

await handle.start()
await handle.finish()

async with handle.span("agent:tool") as span:
    ...
```

### `SpanContext`

The object yielded by span context managers.

```python
async with instance.span("agent:llm") as span:
    span.id                      # -> str
    span.set_payload(data: dict) # queues a payload update
    span.get_payload()           # -> dict (current local payload)
    await span.finish()          # called automatically on context exit
```

`set_payload` is fire-and-forget — it enqueues an update operation immediately and returns without waiting for the HTTP call to complete.

## Configuration

```python
from prefactor_core import PrefactorCoreConfig, QueueConfig
from prefactor_http import HttpClientConfig

config = PrefactorCoreConfig(
    http_config=HttpClientConfig(
        api_url="https://api.prefactor.ai",
        api_token="your-token",
    ),
    queue_config=QueueConfig(
        num_workers=3,        # Number of background workers
        max_retries=3,        # Retries per operation
        retry_delay_base=1.0, # Base delay (seconds) for exponential backoff
    ),
    schema_registry=None,  # Optional: SchemaRegistry instance
)
```

## Schema Registry

Use `SchemaRegistry` to compose span schemas from multiple sources and auto-generate the `agent_schema_version` passed to `create_agent_instance`.

```python
from prefactor_core import SchemaRegistry

registry = SchemaRegistry()

# Full structured form: params schema, result schema, title, description, template
registry.register_type(
    name="agent:llm",
    params_schema={
        "type": "object",
        "properties": {
            "model": {"type": "string"},
            "prompt": {"type": "string"},
        },
        "required": ["model", "prompt"],
    },
    result_schema={
        "type": "object",
        "properties": {"response": {"type": "string"}},
    },
    title="LLM Call",
    description="A call to a language model",
    template="{{model}}: {{prompt}} → {{response}}",
)
registry.register_type(
    name="agent:tool",
    params_schema={"type": "object", "properties": {...}},
    result_schema={"type": "object", "properties": {...}},
    title="Tool Call",
)

config = PrefactorCoreConfig(
    http_config=...,
    schema_registry=registry,
)

async with PrefactorCoreClient(config) as client:
    # agent_schema_version is generated automatically from the registry
    instance = await client.create_agent_instance(
        agent_id="my-agent",
        agent_version={"name": "My Agent", "external_identifier": "v1.0.0"},
    )
```

## Error Handling

```python
from prefactor_core import (
    PrefactorCoreError,
    ClientNotInitializedError,
    ClientAlreadyInitializedError,
    OperationError,
    InstanceNotFoundError,
    SpanNotFoundError,
)
```

## Architecture

The client uses a three-layer design:

1. **Queue infrastructure**: `InMemoryQueue` + `TaskExecutor` worker pool process operations in the background
2. **Managers**: `AgentInstanceManager` and `SpanManager` translate high-level calls into `Operation` objects and route them to the HTTP client
3. **Client API**: `PrefactorCoreClient` exposes the user-facing interface and wires the layers together

All observability operations are enqueued and executed asynchronously — the calling code is never blocked waiting for API responses.

## License

MIT
