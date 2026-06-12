from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from common.schemas import DefenseVerdict, ExperimentConfig, TelemetryMessage, TraceRecord
from agent.agent import HvacAgent


class Defense(ABC):
    """Interface that D1 and D2 defense sidecars must implement."""

    @abstractmethod
    def inspect(self, telemetry: TelemetryMessage) -> DefenseVerdict: ...


class Transport(ABC):
    """Abstraction over in-process and live MQTT backends."""

    @abstractmethod
    def publish_tick(self, telemetry: TelemetryMessage) -> TraceRecord: ...

    @abstractmethod
    def reset(self) -> None: ...


class InProcessTransport(Transport):
    """Deterministic, in-process pipeline — no network I/O."""

    def __init__(
        self,
        agent: HvacAgent,
        config: ExperimentConfig,
        defense: Defense | None = None,
    ) -> None:
        self._agent = agent
        self._config = config
        self._defense = defense
        self._trial = 0

    def reset(self) -> None:
        self._trial = 0

    def publish_tick(self, telemetry: TelemetryMessage) -> TraceRecord:
        verdict = (
            self._defense.inspect(telemetry)
            if self._defense
            else DefenseVerdict(blocked=False)
        )

        tool_calls: list = []
        final_decision: dict = {}
        if not verdict.blocked:
            tool_calls, final_decision = self._agent.run(telemetry)

        trace = TraceRecord(
            trace_id=str(uuid.uuid4()),
            ts=datetime.now(timezone.utc),
            condition=self._config.defense,
            attack_id=self._config.attack_id,
            trial=self._trial,
            inputs_seen=telemetry.model_dump(),
            defense_verdict=verdict,
            tool_calls=tool_calls,
            final_decision=final_decision,
        )
        self._trial += 1
        return trace


class HvacEnv:
    """Gym-like env wrapper satisfying DoomArena's env contract."""

    def __init__(self, transport: Transport, config: ExperimentConfig) -> None:
        self._transport = transport
        self._config = config

    def reset(self) -> None:
        self._transport.reset()

    def step(self, telemetry: TelemetryMessage) -> TraceRecord:
        return self._transport.publish_tick(telemetry)
