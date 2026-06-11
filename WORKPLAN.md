# DoomArena-IoT — Work Plan (2-developer team)

> How the work is sequenced and divided. Pairs with `ARCHITECTURE.md`
> (the design) and `context.md` (the brief).

## Roles

The work is split into two ownership tracks, divided by **vertical responsibility**
(not by phase) so the two developers rarely block each other.

- **Developer 1 — Core & Evaluation.** Owns the vertical "spine": the components
  that produce the Attack Success Rate (ASR) results. This is the critical path —
  every result depends on it. Started first and carries the larger initial load.
- **Developer 2 — Platform & Demo.** Owns the live distributed system and the
  template-following extensions. This work runs in parallel and does not block the
  ASR results.

## Ownership

### Developer 1 — Core & Evaluation (critical path)

Build in this order; each step unblocks the next.

| # | File / area | Description |
|---|-------------|-------------|
| 1 | `common/schemas.py` | The 3 contracts: MQTT message schema, trace schema, config shape (C1/C2/C3 in `ARCHITECTURE.md`). **Defined jointly, first.** |
| 2 | `common/llm_client.py` | `LLMClient` abstraction — `mock` + one real backend. |
| 3 | `common/` → `HvacEnv` + `InProcessTransport` | Deterministic in-process pipeline. |
| 4 | `agent/agent.py` + `agent/tools.py` | The AI agent (the target) and its 5 tools. |
| 5 | `attacks/mqtt_gateway.py` | `MqttAttackGateway` — the new DoomArena passerelle. |
| 6 | `attacks/a1_compromised.py`, `attacks/a2_injection.py` | A1 (plumbing) then A2 (prompt-injection centerpiece) + their `SuccessFilter`s. |
| 7 | `harness/run_experiments.py` + `harness/metrics.py` | Experiment loop, ASR computation, export. |
| 8 | `ingest/ingest.py` (D1), `defense/llm_judge.py` (D2) | Both defenses. |

→ This track alone is sufficient to produce a complete ASR table for the paper.

### Developer 2 — Platform & Demo (parallel, non-blocking)

| File / area | Description |
|-------------|-------------|
| `docker-compose.yml` + Mosquitto config + all `Dockerfile`s | The containerized stack. |
| `MqttTransport` (in `common/`) | Live MQTT backend — powers the `docker compose up` demo. |
| `sensors/sensor_sim.py` | Standalone sensor-publisher container. |
| `attacks/a3_dos.py`, `attacks/a4_coordinated.py` | A3 + A4 — follow the A1/A2 attack + `SuccessFilter` template. |
| `README.md` + `results/` formatting | Run instructions, CSV/table/visualization output. |

## Cross-track dependency

There is **one** true blocker between the tracks: the **3 contracts** (`common/schemas.py`,
C1/C2/C3). Both `InProcessTransport` and `MqttTransport` build against the same
`Transport` interface and trace schema, so these are defined and frozen jointly on
day one. After that, both tracks run independently and produce identical traces.

## Milestones (gated)

| # | Milestone | Done when | Owner |
|---|-----------|-----------|-------|
| M0 | Contracts frozen | C1/C2/C3 reviewed + merged | both (pair) |
| M1 | In-process pipeline + mock LLM | `HvacEnv` runs a tick → valid trace | Dev 1 |
| M2 | Gateway + A1 + first ASR (no defense) | harness prints A1 ASR from a real run | Dev 1 |
| M3 | A2 + D1 + D2 | table shows D1 misses A2, D2 catches it | Dev 1 |
| M4 | Live demo | `docker compose up` runs MqttTransport end-to-end | Dev 2 |
| M5 | A3 + A4 | full 4×3 table | Dev 2 (attacks) + Dev 1 (harness) |
| M6 | Paper-ready | `results/` CSV+JSON exported, README done | both |

**First integration checkpoint = M2.** Gate: in-process env + agent + mock LLM +
gateway + A1 + its `SuccessFilter` are integrated and produce the first ASR number.

## Working agreement

- `git init` + GitHub remote; feature branches per task (`feat/<area>-<thing>`).
- Every PR reviewed by the other developer; `main` always stays `docker compose up`-clean.
- Secrets only in a gitignored `.env`; `.env.example` is committed.
- Fixed random seeds; document the number of trials; every number in the paper
  comes from a real logged run in `results/` — no invented figures.

## Immediate next step

Scaffold **Step 1** (repo skeleton + the 3 contracts + a mock in-process tick) per
`context.md` §11. The contracts (M0) are the prerequisite for all parallel work.
