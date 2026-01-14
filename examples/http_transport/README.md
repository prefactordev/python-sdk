# HTTP Transport Example

This example demonstrates how to use the Prefactor SDK with HTTP transport to send trace spans to the Prefactor backend API.

## Setup

1. Set environment variables:

```bash
export PREFACTOR_API_URL="https://p2demo.prefactor.dev"
export PREFACTOR_API_TOKEN="your-api-token-here"
export PREFACTOR_AGENT_ID="my-agent"  # Optional
export PREFACTOR_AGENT_VERSION="1.0.0"  # Optional
export ANTHROPIC_API_KEY="your-anthropic-api-key"
```

2. Install dependencies:

```bash
pip install -e ".[dev]"
```

## Running the Example

```bash
python examples/http_transport/simple_http.py
```

## Configuration Options

### Option 1: Environment Variables

```python
import os
import prefactor_sdk

os.environ["PREFACTOR_TRANSPORT"] = "http"
os.environ["PREFACTOR_API_URL"] = "https://p2demo.prefactor.dev"
os.environ["PREFACTOR_API_TOKEN"] = "your-token"

middleware = prefactor_sdk.init()
```

### Option 2: Code Configuration

```python
import prefactor_sdk

config = prefactor_sdk.Config(
    transport_type="http",
    api_url="https://p2demo.prefactor.dev",
    api_token="your-token",
    agent_id="my-agent",
    agent_version="1.0.0",
)

middleware = prefactor_sdk.init(config)
```

## How It Works

1. **SDK Initialization**: When you call `prefactor_sdk.init()` with HTTP transport, it:
   - Creates an `HttpTransport` instance
   - Starts a background worker thread with an asyncio event loop
   - Creates an unbounded queue for buffering spans

2. **Agent Registration**: On the first span emission:
   - The transport automatically registers an agent instance with the backend
   - Agent metadata (ID, version, schema) is sent to `/api/v1/agent_instance/register`
   - The returned `agent_instance_id` is stored for subsequent span sends

3. **Span Sending**: When your LangChain agent executes:
   - Spans are created for agent execution, LLM calls, and tool invocations
   - Each span is queued in the transport's buffer
   - The background worker sends spans to `/api/v1/agent_spans` with exponential backoff retry

4. **Graceful Shutdown**: When your program exits:
   - The transport drains remaining spans from the queue (with timeout)
   - Background thread is shut down gracefully

## Features

- **Non-blocking**: HTTP I/O happens in background, never blocks your application
- **Automatic retry**: Failed requests are retried with exponential backoff
- **Thread-safe**: Safe to use from multiple threads
- **Reliable**: Unbounded queue prevents data loss during traffic spikes
- **Graceful degradation**: Network errors are logged, application continues

## Troubleshooting

### "HTTP transport requires api_url parameter"

Make sure you've set `PREFACTOR_API_URL` or passed `api_url` to the Config.

### "HTTP transport requires api_token parameter"

Make sure you've set `PREFACTOR_API_TOKEN` or passed `api_token` to the Config.

### No spans appearing in dashboard

1. Check logs for errors: Look for "Registration failed" or "Failed to send span" messages
2. Verify your API URL and token are correct
3. Ensure your network can reach the Prefactor backend
4. Check that your agent is actually executing (verbose=True helps debug)

### Network errors

The transport will automatically retry on 500 errors and rate limits (429). Check logs for retry messages. If retries are exhausted, spans will be dropped and logged.
