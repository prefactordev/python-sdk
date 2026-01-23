# prefactor-sdk

Prefactor SDK - Automatic observability for LangChain agents. This package provides a unified wrapper around `prefactor-core` and `prefactor-langchain`.

## Installation

```bash
pip install prefactor-sdk
```

## Usage

### Modern Middleware API (Recommended)

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
result = agent.invoke({"messages": [("user", "Hello!")]})
```

### Legacy Callback API

```python
import prefactor_sdk
from langchain_openai import ChatOpenAI

# Initialize callback handler
handler = prefactor_sdk.init_callback()

# Use with LangChain models
llm = ChatOpenAI(model="gpt-4", callbacks=[handler])
response = llm.invoke("Hello!")
```

## Features

- Zero-config tracing
- Automatic span lifecycle management
- Token usage tracking
- Error capture with stack traces
- Support for both modern middleware and legacy callback APIs
