# prefactor-core

Core tracing primitives for Prefactor observability. This package provides framework-agnostic tracing capabilities.

## Installation

```bash
pip install prefactor-core
```

## Usage

```python
from prefactor_core import Tracer, StdioTransport, SpanType

# Create transport and tracer
transport = StdioTransport()
tracer = Tracer(transport=transport)

# Start a span
span = tracer.start_span(
    name="my_operation",
    span_type=SpanType.LLM,
    inputs={"prompt": "Hello"}
)

# End the span
tracer.end_span(span=span, outputs={"response": "Hi!"})
```

## Features

- Thread-safe tracing
- Multiple transport options (STDIO, HTTP)
- Async-safe context propagation
- JSON serialization with truncation support
