# DoomArena-IoT — Architecture & Design Decisions

> Source of truth for *how* we build. Read `context.md` first for *why*.
> Authored by the architect; to be kept current as decisions change.

---

## 1. DoomArena API — verified (not assumed)

Read from the official source (`doomarena.core`, branch `main`). These are the
**real** classes we integrate with:

| Concept        | Real class / base                          | Key signature |
|----------------|--------------------------------------------|---------------|
| Attack         | `Attacks(BaseModel, ABC)`                  | `attack_name: str`; `get_next_attack(**kwargs) -> Any`. Register: `@register_attacks("name")` |
| Example attack | `FixedInjectionAttack`                      | adds `injection_str: str`; returns it from `get_next_attack` |
| Wiring         | `AttackConfig(BaseModel)`                   | `attackable_component: dict`, `attack: Attacks`, `filter: AttackFilter \| None`, `success_filter: SuccessFilter` |
| Gateway        | `AttackGateway(ABC)`                        | `__init__(self, env, attack_configs)`; abstract `reset()`, `step()`; optional `attack_success()`. Delegates unknown attrs to `env`. Register: `@register_attack_gateway("name")` |
| Success / ASR  | `SuccessFilter(BaseModel)`                  | `__call__(...) -> bool`, `setup_success_filter()`, `get_goal_description()` |
| Pre-filter     | `AttackFilter(BaseModel)`                   | `filter_name`, `__call__ -> bool` (decides *when* an attack fires) |
| Defense        | `AttackSafetyCheck(BaseModel, ABC)`         | `defense_name`, `abort_on_detection: bool`, `attack_detected(messages) -> bool` |
| LLM judge ref  | `LLMJudgeSafetyCheck.check(messages)`       | uses `OPENROUTER_API_KEY` + `gpt-4o` in their example (we abstract this) |

**Mapping to our project**
- Our 4 attacks (`attacks/a*.py`) subclass `Attacks`.
- `attack_succeeded()` from the brief becomes `SuccessFilter` subclasses.
- D2 reuses the `AttackSafetyCheck` interface.
- The only thing we genuinely invent: **`MqttAttackGateway(AttackGateway)`** — the
  new MQTT passerelle DoomArena doesn't ship.

---

## 2. Execution model — HYBRID (decided)

DoomArena's gateway wraps a **synchronous, gym-like `env`** (`reset()`/`step()`).
Our cloud-architecture story needs a **distributed async MQTT system**. We satisfy
both with one `env` abstraction over two transports:

```
            DoomArena AttackGateway (MqttAttackGateway)
                          │ wraps
                          ▼
                       HvacEnv            reset() / step()
                          │ uses
                          ▼
                    Transport (interface)
                   /                    \
        InProcessTransport          MqttTransport
   (direct calls; deterministic;   (real Mosquitto + containers;
    used by the harness for ASR)    the `docker compose up` demo)
```

- `HvacEnv.step()` = "publish one telemetry tick (attack injected into the
  free-text `description` field) → wait for the agent's decision → return the
  trace."
- **Same** agent / defense / attack / success-filter code runs on both
  transports. Only the transport swaps.
- **ASR numbers come from `InProcessTransport`** (seedable, fast, no broker flake).
- **The demo / architecture artifact is `MqttTransport`** over Docker Compose.

Rationale: reproducible measurements *and* a defensible distributed-systems
design, without duplicating logic.

---

## 3. The three contracts (freeze these FIRST)

Everything decouples around these. They live in `common/` and are written before
either track builds behind them.

### C1 — MQTT topic + message schema (`common/schemas.py`)
- Topics: `telemetry/<room_id>/<sensor_id>` (extend as needed).
- Telemetry envelope (pydantic), **must** keep the free-text injection field:
  ```jsonc
  {
    "sensor_id": "temp-01",
    "room_id": "room-a",
    "ts": "<iso8601>",
    "metric": "temperature",
    "value": 21.4,            // numeric reading
    "unit": "C",
    "description": "..."      // FREE TEXT — the A2 injection vector. Never drop it.
  }
  ```
- Actuator / decision event schema (see C2).

### C2 — Trace schema (the measurement boundary)
ASR is computed **only** from traces. One trace per agent decision:
```jsonc
{
  "trace_id": "...",
  "ts": "...",
  "condition": "none|D1|D2",
  "attack_id": "none|A1|A2|A3|A4",
  "trial": 0,
  "inputs_seen": { /* telemetry the agent actually received post-defense */ },
  "defense_verdict": { "blocked": false, "reason": null },
  "tool_calls": [ { "name": "set_thermostat", "args": {"room_id":"room-a","temp":30} } ],
  "final_decision": { /* setpoints */ },
  "notes": "..."
}
```
This is the seam between "build the system" (Track A) and "measure attacks"
(Track B). Owned by the security/eval track but agreed jointly.

### C3 — Transport interface + defense-toggle config
- `Transport` interface: `publish_tick(telemetry) -> trace` (in-process) /
  pub-sub (MQTT). Both yield a **C2 trace**.
- `config.yaml`: `defense: none | D1 | D2`. **Toggling a defense must never touch
  agent code** — the agent is the cible, it doesn't know which defense is active.

---

## 4. LLM strategy

`LLMClient` abstraction (`common/llm_client.py`), backend by env var:
`LLM_BACKEND = mock | anthropic | openai | ollama`, plus `LLM_MODEL`, `LLM_API_KEY`.

- **mock** — deterministic, no network, used for dev + CI. Default.
- **anthropic / openai** — real numbers for the paper. Use a *cheap* model
  (`gpt-4o-mini` / `claude-haiku`). Full experiment cost < ~$2.
- **ollama** — local, zero cost. Recommended for the **D2 judge** (binary
  classification). Use with caution for the **agent** (small models call tools
  unreliably → contaminates ASR). Good for a cost/efficacy bonus result + future
  work.

> NOTE: Claude Pro / ChatGPT Plus subscriptions do **not** grant API access.
> Real runs need an API key (separate pay-as-you-go billing) or Ollama.

Never commit keys. Secrets live only in a gitignored `.env` (see its inline
comments and the README for the available variables).

---

## 5. Defenses

- **D1 (cheap, local)** — in `ingest/`: JSON schema validation + statistical
  bounds (e.g. temp ∈ [−30, 50] °C) + per-sensor rate limiting (A3). Catches
  A1/A3 well; misses A2 by design.
- **D2 (LLM judge)** — `defense/llm_judge.py` implementing `AttackSafetyCheck`;
  inspects the `description` field before the agent acts. Catches A2.

Both are **sidecars toggled by config** (C3), never edits to the agent.

---

## 6. Non-negotiables (from the brief)

- `docker compose up` must just work; `main` always stays demo-clean.
- Fixed seeds; N trials documented; **every number in the paper comes from a real
  logged run in `results/`** — no invented figures.
- No real exploits; attacks are local inert simulations.
