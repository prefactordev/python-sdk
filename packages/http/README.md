# Prefactor HTTP Client

A high-level async HTTP client library for the Prefactor API.

## Features

- **AgentInstance Endpoints**: Register, start, and finish agent instances
- **AgentSpan Endpoints**: Create and finish agent spans
- **Bulk API**: Execute multiple operations in a single request
- **Automatic Retries**: Exponential backoff with jitter for transient failures
- **Type Safety**: Full Pydantic models for all request/response data
- **Proper Error Handling**: Clear exception hierarchy for different error types
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
    # Configure the client
    config = HttpClientConfig(
        api_url="https://api.prefactor.ai",
        api_token="your-api-token",
    )

    # Use as async context manager
    async with PrefactorHttpClient(config) as client:
        # Make a POST request
        response = await client.request(
            method="POST",
            path="/api/v1/agent_spans",
            json_data={
                "agent_instance_id": "instance_123",
                "schema_name": "llm",
                "payload": {"model": "gpt-4"}
            }
        )
        print(response)

asyncio.run(main())
```

## Usage Examples

### Register an Agent Instance

```python
from datetime import datetime

async with PrefactorHttpClient(config) as client:
    response = await client.request(
        method="POST",
        path="/api/v1/agent_instance/register",
        json_data={
            "agent_id": "agent_123",
            "agent_version": {
                "name": "Customer Support Bot",
                "external_identifier": "v1.0.0",
                "description": "Production release"
            },
            "agent_schema_version": {
                "external_identifier": "schema-v1",
                "span_schemas": {
                    "llm": {"type": "object", "properties": {...}},
                    "tool": {"type": "object", "properties": {...}}
                }
            }
        }
    )
    instance_id = response["details"]["id"]
    print(f"Created instance: {instance_id}")
```

### Start and Finish an Instance

```python
async with PrefactorHttpClient(config) as client:
    # Start the instance
    await client.request(
        method="POST",
        path=f"/api/v1/agent_instance/{instance_id}/start"
    )
    
    # ... do work ...
    
    # Finish the instance
    await client.request(
        method="POST",
        path=f"/api/v1/agent_instance/{instance_id}/finish"
    )
```

### Create and Finish a Span

```python
async with PrefactorHttpClient(config) as client:
    # Create a span
    response = await client.request(
        method="POST",
        path="/api/v1/agent_spans",
        json_data={
            "agent_instance_id": "instance_123",
            "schema_name": "llm",
            "payload": {
                "model": "gpt-4",
                "prompt": "Hello, world!"
            }
        }
    )
    span_id = response["details"]["id"]
    
    # Later, finish the span
    await client.request(
        method="POST",
        path=f"/api/v1/agent_spans/{span_id}/finish"
    )
```

### Using Idempotency Keys

Idempotency keys ensure that duplicate requests are handled safely. If a request with the same key is received, the API returns the original response without reprocessing. This is useful for preventing duplicate actions when retries occur.

```python
import uuid
from prefactor_http import PrefactorHttpClient, HttpClientConfig

async def create_span_with_idempotency():
    config = HttpClientConfig(
        api_url="https://api.prefactor.ai",
        api_token="your-api-token",
    )

    async with PrefactorHttpClient(config) as client:
        # Generate a unique idempotency key for this operation
        # Use the same key to safely retry this exact operation
        idempotency_key = str(uuid.uuid4())
        
        try:
            response = await client.request(
                method="POST",
                path="/api/v1/agent_spans",
                json_data={
                    "agent_instance_id": "instance_123",
                    "schema_name": "llm",
                    "payload": {
                        "model": "gpt-4",
                        "prompt": "Process payment of $50.00"
                    }
                },
                idempotency_key=idempotency_key
            )
            print(f"Created span: {response['details']['id']}")
        except PrefactorRetryExhaustedError:
            # Even if all retries failed, the request may have succeeded
            # before the error occurred. When you retry with the same
            # idempotency key, the API will return the original success
            # response instead of creating a duplicate span.
            print("Request failed, but may have succeeded on the server")

# You can safely retry the same operation with the same key
asyncio.run(create_span_with_idempotency())
```

**When to use idempotency keys:**
- Creating spans that represent payments or other non-idempotent operations
- Any operation where duplicate execution would cause problems
- When you need to safely retry failed requests without side effects

**Best practices:**
- Generate a new UUID for each distinct operation
- Reuse the same key when retrying the same operation
- Keys are automatically sent as the `Idempotency-Key` HTTP header
- The API guarantees at-least-once execution with exactly-once semantics when using idempotency keys

## Error Handling

The client provides specific exception types for different error scenarios:

```python
from prefactor_http import (
    PrefactorHttpClient,
    HttpClientConfig,
    PrefactorApiError,
    PrefactorAuthError,
    PrefactorNotFoundError,
    PrefactorValidationError,
    PrefactorRetryExhaustedError,
)

async def handle_errors():
    try:
        async with PrefactorHttpClient(config) as client:
            response = await client.request(
                method="POST",
                path="/api/v1/agent_instance/register",
                json_data={...}
            )
    except PrefactorValidationError as e:
        print(f"Validation error: {e.errors}")
    except PrefactorAuthError:
        print("Authentication failed")
    except PrefactorRetryExhaustedError:
        print("Request failed after retries")
    except PrefactorApiError as e:
        print(f"API error {e.status_code}: {e.code}")
```

## Configuration

### Retry Configuration

Customize retry behavior:

```python
config = HttpClientConfig(
    api_url="https://api.prefactor.ai",
    api_token="token",
    max_retries=5,
    initial_retry_delay=0.5,
    max_retry_delay=30.0,
    retry_multiplier=1.5,
)
```

### Timeout Configuration

Set custom timeouts:

```python
config = HttpClientConfig(
    api_url="https://api.prefactor.ai",
    api_token="token",
    request_timeout=60.0,    # Total request timeout
    connect_timeout=15.0,     # Connection timeout
)
```

## Bulk Operations

The Bulk API allows you to execute multiple operations in a single HTTP request, reducing round trips and improving performance.

### Executing Bulk Requests

```python
from prefactor_http import BulkRequest, BulkItem

async with PrefactorHttpClient(config) as client:
    # Create a bulk request with multiple operations
    request = BulkRequest(
        items=[
            BulkItem(
                _type="agents/list",
                idempotency_key="list-agents-001",
                environment_id="env_abc123"
            ),
            BulkItem(
                _type="agents/create",
                idempotency_key="create-agent-001",
                environment_id="env_abc123",
                details={
                    "name": "Customer Support Bot",
                    "description": "Handles customer inquiries"
                }
            ),
            BulkItem(
                _type="agents/show",
                idempotency_key="show-agent-001",
                agent_id="agent_xyz789"
            )
        ]
    )
    
    # Execute the bulk request
    response = await client.bulk.execute(request)
    
    # Access results by idempotency_key
    for key, output in response.outputs.items():
        print(f"{key}: {output.status}")
        if output.status == "success":
            # Access operation-specific data
            if hasattr(output, 'summaries'):
                print(f"  Found {len(output.summaries)} items")
            elif hasattr(output, 'details'):
                print(f"  Created: {output.details.id}")
```

### Bulk Request Validation

- Each item must have a unique `idempotency_key` (min 8, max 64 characters)
- All items in a request must have unique keys
- The request must contain at least one item

```python
from prefactor_http import BulkRequest, BulkItem

# Validation example
try:
    request = BulkRequest(
        items=[
            BulkItem(
                _type="agents/list",
                idempotency_key="list-key-001",
                environment_id="env_123"
            ),
            BulkItem(
                _type="agents/list",
                idempotency_key="list-key-001",  # Same key - will raise error
                environment_id="env_456"
            )
        ]
    )
except ValueError as e:
    print(f"Validation error: {e}")
```

### Supported Operation Types

Bulk items can use any query or action type supported by the API:
- `agents/list`, `agents/show`, `agents/create`, `agents/update`
- `environments/list`, `environments/show`, `environments/create`, `environments/update`
- `agent_instances/list`, `agent_instances/show`
- `agent_spans/list`, `agent_spans/create`
- And more...

Each operation type requires specific additional parameters beyond `_type` and `idempotency_key`.

## Available Endpoints

This client supports the following POST endpoints:

### Agent Instance
- `POST /api/v1/agent_instance/register` - Register a new agent instance
- `POST /api/v1/agent_instance/{id}/start` - Mark an instance as started
- `POST /api/v1/agent_instance/{id}/finish` - Mark an instance as finished

### Agent Span
- `POST /api/v1/agent_spans` - Create a new agent span
- `POST /api/v1/agent_spans/{id}/finish` - Mark a span as finished

### Bulk
- `POST /api/v1/bulk` - Execute multiple queries/actions in a single request

## License

MIT
