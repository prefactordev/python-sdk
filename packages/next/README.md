# Prefactor Next

Next-generation Prefactor SDK with async queue-based operations.

## Features

- **Asynchronous Queue-Based Processing**: All operations are queued and processed asynchronously
- **Non-Blocking API**: Returns immediately, zero impact on agent execution
- **Stack-Based Span Management**: Automatic parent detection for nested spans
- **Extensible Queue Interface**: Easy to add persistent queue backends
- **First-Class AgentInstance API**: Clean interface for managing agent lifecycles

## Installation

```bash
pip install prefactor-next
```

## Quick Start

```python
import asyncio
from prefactor_next import PrefactorNextClient
from prefactor_http import HttpClientConfig

async def main():
    config = HttpClientConfig(
        api_url="https://api.prefactor.ai",
        api_token="your-token",
    )
    
    async with PrefactorNextClient(config) as client:
        # Create agent instance
        instance = await client.create_agent_instance(
            agent_id="my-agent",
            agent_version={"name": "My Agent", "external_identifier": "v1.0.0"},
            agent_schema_version={"external_identifier": "v1.0.0", "span_schemas": {}},
        )
        
        await instance.start()
        
        # Create spans
        async with instance.span("llm") as span:
            span.set_payload({"model": "gpt-4"})
            result = await call_llm()
            span.set_payload({"response": result})
        
        await instance.finish()

asyncio.run(main())
```

## Architecture

The SDK follows stratified design principles with three layers:

1. **Foundation (Layer 1)**: Queue infrastructure and span context stack
2. **Operations (Layer 2)**: Business logic for instances and spans
3. **API (Layer 3)**: User-facing client interface

## License

MIT
