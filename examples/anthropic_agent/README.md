# Anthropic Agent Example

This example demonstrates end-to-end tracing of a LangChain agent using Anthropic's Claude model with the Prefactor SDK. It serves as a smoke test to verify that the SDK correctly captures agent operations including LLM calls, tool executions, and chains.

## Purpose

- **End-to-End Validation**: Proves the Prefactor SDK works with Anthropic's Claude models
- **Smoke Test**: Can be run to verify SDK functionality after changes
- **Real API Usage**: Uses the live Anthropic API (no mocking)
- **Simple Example**: Demonstrates basic agent functionality with 2 simple tools

## Prerequisites

- Python 3.12 or higher
- Anthropic API key
- Dependencies installed

## Setup

### 1. Install Dependencies

```bash
pip install -e ".[dev]"
```

This will install the Prefactor SDK along with:
- `langchain` - For agent creation
- `langchain-anthropic` - For Claude model integration
- `langchain-core` - For core LangChain functionality

### 2. Set Environment Variables

Set your Anthropic API key:

```bash
export ANTHROPIC_API_KEY=your_api_key_here
```

Or create a `.env` file in the `examples/` directory (see `.env.example`).

## Running the Example

```bash
python examples/anthropic_agent/simple_agent.py
```

## Expected Output

When you run the example, you'll see:

1. **Initialization Messages**: Confirming the SDK and model are set up
2. **Agent Interactions**: Two example interactions showing the agent using tools
3. **Trace Spans**: Newline-delimited JSON output to stdout

### Example Interaction Output

```
================================================================================
Example 1: Getting Current Time
================================================================================

> Entering new agent chain...
[Agent reasoning and tool calls will appear here]

Agent Response:
The current date and time is 2026-01-13 15:30:45
```

### Trace Spans Output

The SDK emits trace spans as newline-delimited JSON to stdout. Each span represents an operation in your agent:

```json
{"span_id": "abc123", "trace_id": "xyz789", "span_type": "chain", ...}
{"span_id": "def456", "trace_id": "xyz789", "span_type": "llm", "parent_span_id": "abc123", ...}
{"span_id": "ghi789", "trace_id": "xyz789", "span_type": "tool", "parent_span_id": "abc123", ...}
```

## Understanding the Traces

### Span Types

You should see three types of spans in the output:

1. **CHAIN**: Represents the agent graph operations from `create_agent`
   - Top-level span for each agent invocation
   - Contains other spans as children

2. **LLM**: Represents calls to Claude via ChatAnthropic
   - Includes `token_usage` field with prompt_tokens, completion_tokens, and total_tokens
   - Shows the model's reasoning and decision-making

3. **TOOL**: Represents tool executions
   - One span for each tool call (calculator, get_current_time)
   - Shows tool input and output

### Span Hierarchy

Spans are organized in a parent-child hierarchy:

- The `trace_id` field groups all spans from a single agent invocation
- The `parent_span_id` field links child spans to their parent
- Example hierarchy:
  ```
  CHAIN (agent execution)
  ├── LLM (initial reasoning)
  ├── TOOL (get_current_time)
  └── LLM (final response)
  ```

### Token Usage

LLM spans include token usage information:

```json
{
  "span_type": "llm",
  "token_usage": {
    "prompt_tokens": 150,
    "completion_tokens": 25,
    "total_tokens": 175
  }
}
```

This helps you track API costs and model usage.

## Tools in This Example

### 1. Calculator Tool
- Evaluates simple mathematical expressions
- Example: "What is 42 multiplied by 17?"

### 2. Time Tool
- Returns the current date and time
- Example: "What is the current date and time?"

## Model Details

This example uses `claude-haiku-4-5-20251001`, which is:
- The latest Claude Haiku model
- Fast and cost-effective
- Supports native tool calling
- Good for smoke testing

## Validation Checklist

The example validates that:
- ✅ LLM spans are created for Claude API calls
- ✅ Tool spans are created for tool executions
- ✅ Chain spans are created for agent operations
- ✅ Parent-child relationships are correct (nested spans)
- ✅ Token usage is captured for Claude calls
- ✅ All spans have proper trace_id grouping

## Troubleshooting

### Missing API Key

```
ValueError: ANTHROPIC_API_KEY environment variable is required.
```

**Solution**: Set the `ANTHROPIC_API_KEY` environment variable.

### Import Errors

```
ModuleNotFoundError: No module named 'langchain_anthropic'
```

**Solution**: Install dev dependencies with `pip install -e ".[dev]"`

### No Trace Output

If you don't see JSON trace spans in stdout, check:
- The Prefactor SDK is properly initialized
- The middleware is passed to `create_agent()`
- Stdout is not being redirected or buffered

## Next Steps

- Try adding your own custom tools
- Experiment with different Claude models (Sonnet, Opus)
- Modify the system prompt to change agent behavior
- Use the traces to analyze agent performance and costs
