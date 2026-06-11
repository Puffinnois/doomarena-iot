# Project Plan

> Developer 1 critical path: build the in-process pipeline that produces the ASR table for the DoomArena-IoT paper.

## Conventions
- Tasks are worked top-to-bottom unless dependencies dictate otherwise.
- `[ ]` = todo, `[~]` = in progress, `[x]` = done.
- Design spec: `docs/superpowers/specs/2026-06-11-dev1-core-evaluation-design.md`
- Architecture: `ARCHITECTURE.md` | Brief: `context.md` | Workplan: `WORKPLAN.md`

## Phase 1: Contracts & Foundations (M0 → M1)

- [ ] [backend] Scaffold repo: `pyproject.toml`, `.env.example`, `config.yaml`, `results/` dir, empty package `__init__.py` files for all modules
- [ ] [backend] Implement `common/schemas.py`: `TelemetryMessage` (C1), `TraceRecord` + `DefenseVerdict` + `ToolCall` (C2), `ExperimentConfig` (C3) — all Pydantic models
- [ ] [backend] Implement `common/llm_client.py`: `LLMClient` with `mock`, `anthropic`, `openai`, `ollama` backends; mock backend is seeded + deterministic

## Phase 2: In-Process Environment (M1)

- [ ] [backend] Implement `common/env.py`: `Transport` ABC, `InProcessTransport`, `HvacEnv` (`reset()`/`step()`) — in-process pipeline, no broker
- [ ] [backend] Implement `agent/tools.py`: 5 tool stubs (`read_temperature`, `check_energy_price`, `read_calendar`, `set_thermostat`, `send_alert`) backed by seeded in-memory state
- [ ] [backend] Implement `agent/agent.py`: LLM loop — build prompt from telemetry, call `LLMClient` with tools, dispatch tool calls, return `TraceRecord`
- [ ] [review] Verify M1 milestone: `HvacEnv` runs one tick with mock LLM and produces a valid `TraceRecord`

## Phase 3: Gateway & Attacks A1/A2 (M2 → M3)

- [ ] [backend] Implement `attacks/mqtt_gateway.py`: `MqttAttackGateway(AttackGateway)` registered as `"mqtt"`, wires `AttackConfig` list into `HvacEnv`
- [ ] [backend] Implement `attacks/a1_compromised.py`: `CompromisedSensorAttack` + `A1SuccessFilter` (thermostat > 28 °C)
- [ ] [backend] Implement `attacks/a2_injection.py`: `PromptInjectionAttack` + `A2SuccessFilter` (same threshold)

## Phase 4: Harness & First ASR (M2)

- [ ] [backend] Implement `harness/metrics.py`: `asr()`, `export_csv()`, `export_json()`
- [ ] [backend] Implement `harness/run_experiments.py`: outer loop over conditions × attacks × trials; prints ASR table; exports to `results/`
- [ ] [review] Verify M2 milestone: harness prints A1 ASR from a real no-defense run; results land in `results/`

## Phase 5: Defenses D1 & D2 (M3)

- [ ] [backend] Implement `ingest/ingest.py`: D1 `AttackSafetyCheck` — schema validation + value bounds `[-30, 50]` °C + per-sensor rate limiting
- [ ] [backend] Implement `defense/llm_judge.py`: D2 `AttackSafetyCheck` — LLM judge on `description` field, binary verdict, `abort_on_detection=True`
- [ ] [review] Verify M3 milestone: full 2×3 table (A1+A2 × none/D1/D2) shows D1 misses A2, D2 catches it

## Backlog / Ideas
- [ ] [infra] Developer 2: `docker-compose.yml`, Mosquitto config, all Dockerfiles
- [ ] [backend] Developer 2: `common/mqtt_transport.py` — live `MqttTransport` backend
- [ ] [backend] Developer 2: `sensors/sensor_sim.py` — standalone sensor publisher
- [ ] [backend] Developer 2: `attacks/a3_dos.py` + `attacks/a4_coordinated.py`
- [ ] [docs] `README.md`: `docker compose up` instructions, how to run experiments, how to read results
