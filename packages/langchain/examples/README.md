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
- Prefactor API URL and token
- Dependencies installed

## Setup

### 1. Install Dependencies

From the `packages/langchain` directory:

```bash
pip install -e ".[dev]"
```

Or install the required packages directly:

```bash
pip install prefactor-langchain langchain
```

### 2. Set Environment Variables

```bash
export ANTHROPIC_API_KEY=your_api_key_here
export PREFACTOR_API_URL=https://api.prefactor.ai
export PREFACTOR_API_TOKEN=your_token_here
```

Or create a `.env` file in the `examples/` directory (see `.env.example`).

## Running the Example

From the `packages/langchain/examples/` directory:

```bash
python simple_agent.py
```

Or from the repository root:

```bash
python packages/langchain/examples/simple_agent.py
```

## Expected Output

When you run the example, you'll see:

1. **Initialization Messages**: Confirming the middleware and agent are set up
2. **Agent Interactions**: Two example interactions showing the agent using tools
3. **Confirmation**: Messages indicating traces are being sent to Prefactor

### Example Interaction Output

```
================================================================================
Prefactor SDK - Anthropic Agent Example
================================================================================

Initializing Prefactor middleware...
✓ Prefactor middleware initialized

Creating agent with Prefactor tracing enabled...
✓ Agent created with tracing enabled

================================================================================
Example 1: Getting Current Time
================================================================================

Agent Response:
The current date and time is 2026-01-13 15:30:45

================================================================================
Example 2: Simple Calculation
================================================================================

Agent Response:
The result of 42 multiplied by 17 is 714.

================================================================================
Example Complete!
================================================================================

Traces have been sent to Prefactor.
Check your Prefactor dashboard to view:
  - Agent execution spans
  - LLM call spans with token usage
  - Tool execution spans

Shutting down...
✓ Complete
```

## Understanding the Traces

Traces are automatically sent to the Prefactor API. You can view them in the Prefactor dashboard.

### Span Types

You should see three types of spans:

1. **AGENT**: Represents the agent execution
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
  AGENT (agent execution)
  ├── LLM (initial reasoning)
  ├── TOOL (get_current_time)
  └── LLM (final response)
  ```

### Token Usage

LLM spans include token usage information:

```json
{
  "type": "langchain:llm",
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

This example uses `claude-sonnet-4-5-20250929`, which is:
- The Claude Sonnet model (balanced performance and cost)
- Supports native tool calling
- Good for smoke testing

## Validation Checklist

The example validates that:
- ✅ PrefactorMiddleware initializes correctly with api_url and api_token
- ✅ LLM spans are created for Claude API calls
- ✅ Tool spans are created for tool executions
- ✅ Agent spans are created for agent operations
- ✅ Parent-child relationships are correct (nested spans)
- ✅ Token usage is captured for Claude calls
- ✅ All spans are sent to the Prefactor API

## Troubleshooting

### Missing API Key

```
ValueError: ANTHROPIC_API_KEY environment variable is required.
```

**Solution**: Set the `ANTHROPIC_API_KEY` environment variable.

### Missing Prefactor Token

```
ValueError: PREFACTOR_API_TOKEN environment variable is required.
```

**Solution**: Set the `PREFACTOR_API_TOKEN` environment variable.

### Import Errors

```
ModuleNotFoundError: No module named 'langchain_anthropic'
```

**Solution**: Install dependencies with `pip install langchain-anthropic`

### No Traces in Dashboard

If you don't see traces in the Prefactor dashboard:
- Check that `PREFACTOR_API_URL` and `PREFACTOR_API_TOKEN` are correct
- Verify network connectivity to the Prefactor API
- Run with debug logging to see what's being sent

## Next Steps

- Try adding your own custom tools
- Experiment with different Claude models (Haiku, Sonnet, Opus)
- Modify the system prompt to change agent behavior
- Use the traces to analyze agent performance and costs
- Explore the Prefactor dashboard to visualize traces
