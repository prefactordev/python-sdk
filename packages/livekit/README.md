# prefactor-livekit

LiveKit Agents integration for Prefactor observability. This package wraps
`livekit-agents` sessions and emits Prefactor spans from public LiveKit session
events.

## Installation

```bash
pip install prefactor-livekit
```

## Usage

### Factory pattern

```python
from livekit.agents import AgentSession
from prefactor_livekit import PrefactorLiveKitSession

session = AgentSession(...)

tracer = PrefactorLiveKitSession.from_config(
    api_url="https://api.prefactor.ai",
    api_token="your-api-token",
    agent_id="voice-agent",
    agent_name="Voice Agent",
)

await tracer.start(session=session, agent=my_agent)
await tracer.close()
```

### Example runner

The example script has a local smoke mode that emits representative LiveKit
session events into Prefactor without needing STT/TTS providers or a room.

```bash
uv run python packages/livekit/examples/simple_session.py --mode smoke
```

It prints the Prefactor instance ID plus ready-to-run Prefactor CLI commands
for retrieving the instance and listing spans for the example's time window.

```bash
prefactor agent_instances retrieve <instance-id>
prefactor agent_spans list \
  --agent_instance_id <instance-id> \
  --start_time <recent-start-time> \
  --end_time <recent-end-time> \
  --include_summaries
```

There is also a model-backed mode for a real text turn:

```bash
uv run python packages/livekit/examples/simple_session.py \
  --mode live \
  --model anthropic/claude-sonnet-4-5-20250929
```

### Manual attachment

Use this when your app manages the session lifecycle itself and you just want
the LiveKit events traced.

```python
from prefactor_livekit import PrefactorLiveKitSession

tracer = PrefactorLiveKitSession(instance=instance)
await tracer.attach(session)

await session.generate_reply(user_input="hello")

await tracer.close()
```

## Traced span types

- `livekit:session`
- `livekit:user_turn`
- `livekit:assistant_turn`
- `livekit:tool`
- `livekit:llm`
- `livekit:stt`
- `livekit:tts`
- `livekit:state`
- `livekit:error`

## Development

```bash
uv run pytest packages/livekit/tests -v
```
