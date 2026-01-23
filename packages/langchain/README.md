# prefactor-langchain

LangChain integration for Prefactor observability. This package provides automatic tracing for LangChain agents.

## Installation

```bash
pip install prefactor-langchain
```

## Usage

### Middleware API (Recommended for LangChain 1.0+)

```python
from prefactor_langchain import PrefactorMiddleware
from prefactor_core import Tracer, StdioTransport

# Create tracer
transport = StdioTransport()
tracer = Tracer(transport=transport)

# Create middleware
middleware = PrefactorMiddleware(tracer=tracer)

# Use with create_agent()
```

### Callback Handler API (Legacy)

```python
from prefactor_langchain import PrefactorCallbackHandler
from prefactor_core import Tracer, StdioTransport
from langchain_openai import ChatOpenAI

# Create tracer and handler
transport = StdioTransport()
tracer = Tracer(transport=transport)
handler = PrefactorCallbackHandler(tracer=tracer)

# Use with LangChain models
llm = ChatOpenAI(model="gpt-4", callbacks=[handler])
```

## Features

- Automatic LLM call tracing
- Tool execution tracing
- Token usage capture
- Error tracking with stack traces
