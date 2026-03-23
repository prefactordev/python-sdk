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
