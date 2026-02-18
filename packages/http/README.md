# Prefactor HTTP Client

A low-level async HTTP client for the Prefactor API.

## Features

- **Typed Endpoint Clients**: Dedicated clients for agent instances, agent spans, and bulk operations
- **Automatic Retries**: Exponential backoff with jitter for transient failures
- **Type Safety**: Full Pydantic models for all request/response data
- **Clear Error Hierarchy**: Specific exception types for different failure modes
- **Idempotency**: Built-in support for idempotency keys

## Installation

```bash
pip install prefactor-http
```

## Quick Start

```python
import asyncio
from prefactor_http import PrefactorHttpClient, HttpClientConfig

async def main():
    config = HttpClientConfig(
        api_url="https://api.prefactor.ai",
        api_token="your-api-token",
    )

    async with PrefactorHttpClient(config) as client:
        instance = await client.agent_instances.register(
            agent_id="agent_123",
            agent_version={"name": "My Agent", "external_identifier": "v1.0.0"},
            agent_schema_version={"external_identifier": "v1.0.0", "span_schemas": {}},
        )
        print(f"Registered instance: {instance.id}")

asyncio.run(main())
```

## Endpoints

### Agent Instances (`client.agent_instances`)

```python
# Register a new agent instance
instance = await client.agent_instances.register(
    agent_id="agent_123",
    agent_version={
        "name": "My Agent",
        "external_identifier": "v1.0.0",
        "description": "Optional description",
    },
    agent_schema_version={
        "external_identifier": "schema-v1",
        "span_schemas": {
            "agent:llm": {"type": "object", "properties": {...}},
        },
    },
    id=None,                      # Optional: pre-assign an ID
    idempotency_key=None,         # Optional: idempotency key
    update_current_version=True,  # Optional: update the agent's current version
)

# Start an instance
instance = await client.agent_instances.start(
    agent_instance_id=instance.id,
    timestamp=None,       # Optional: override start time
    idempotency_key=None,
)

# Finish an instance
instance = await client.agent_instances.finish(
    agent_instance_id=instance.id,
    status=None,          # Optional: "complete" | "failed" | "cancelled"
    timestamp=None,       # Optional: override finish time
    idempotency_key=None,
)
```

The `AgentInstance` response includes: `id`, `agent_id`, `status`, `started_at`, `finished_at`, `span_counts`, and more.

### Agent Spans (`client.agent_spans`)

```python
# Create a span
span = await client.agent_spans.create(
    agent_instance_id="instance_123",
    schema_name="agent:llm",
    status="active",
    payload={"model": "gpt-4", "prompt": "Hello"},  # Optional
    result_payload=None,                              # Optional
    id=None,                                          # Optional: pre-assign an ID
    parent_span_id=None,                              # Optional: parent for nesting
    started_at=None,                                  # Optional: override start time
    finished_at=None,
    idempotency_key=None,
)

# Finish a span
span = await client.agent_spans.finish(
    agent_span_id=span.id,
    status=None,           # Optional: "complete" | "failed" | "cancelled"
    result_payload=None,   # Optional: final result data
    timestamp=None,        # Optional: override finish time
    idempotency_key=None,
)
```

The `AgentSpan` response includes: `id`, `agent_instance_id`, `schema_name`, `status`, `payload`, `result_payload`, `parent_span_id`, `started_at`, `finished_at`, and more.

### Bulk Operations (`client.bulk`)

Execute multiple POST actions in a single HTTP request.

```python
from prefactor_http import BulkRequest, BulkItem

request = BulkRequest(
    items=[
        BulkItem(
            _type="agent_instances/register",
            idempotency_key="register-instance-001",
            agent_id="agent_123",
            agent_version={"name": "My Agent", "external_identifier": "v1.0.0"},
            agent_schema_version={"external_identifier": "v1.0.0", "span_schemas": {}},
        ),
        BulkItem(
            _type="agent_spans/create",
            idempotency_key="create-span-001",
            agent_instance_id="instance_123",
            schema_name="agent:llm",
            status="active",
        ),
    ]
)

response = await client.bulk.execute(request)

for key, output in response.outputs.items():
    print(f"{key}: {output.status}")  # "success" or "error"
```

**Validation rules:**
- Each item must have a unique `idempotency_key` (8–64 characters)
- The request must contain at least one item

## Error Handling

```python
from prefactor_http import (
    PrefactorHttpError,
    PrefactorApiError,
    PrefactorAuthError,
    PrefactorNotFoundError,
    PrefactorValidationError,
    PrefactorRetryExhaustedError,
    PrefactorClientError,
)

try:
    async with PrefactorHttpClient(config) as client:
        instance = await client.agent_instances.register(...)
except PrefactorValidationError as e:
    print(f"Validation error: {e.errors}")
except PrefactorAuthError:
    print("Authentication failed - check your API token")
except PrefactorNotFoundError:
    print("Resource not found")
except PrefactorRetryExhaustedError as e:
    print(f"Request failed after retries: {e.last_error}")
except PrefactorApiError as e:
    print(f"API error {e.status_code}: {e.code}")
```

## Configuration

```python
config = HttpClientConfig(
    # Required
    api_url="https://api.prefactor.ai",
    api_token="your-token",

    # Retry behavior
    max_retries=3,
    initial_retry_delay=1.0,
    max_retry_delay=60.0,
    retry_multiplier=2.0,

    # Timeouts
    request_timeout=30.0,
    connect_timeout=10.0,
)
```

## Types

```python
from prefactor_http import AgentStatus, FinishStatus

# AgentStatus = Literal["pending", "active", "complete", "failed", "cancelled"]
# FinishStatus = Literal["complete", "failed", "cancelled"]
```

## License

MIT
