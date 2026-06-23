from __future__ import annotations
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel


class TelemetryMessage(BaseModel):
    sensor_id: str
    room_id: str
    ts: datetime
    metric: str
    value: float
    unit: str
    description: str  # FREE TEXT — A2 injection vector; never optional
    burst_seq: int = 0  # A3: position of this message within a simulated flood burst; 0 = no burst


class ToolCall(BaseModel):
    name: str
    args: dict[str, Any]


class DefenseVerdict(BaseModel):
    blocked: bool
    reason: str | None = None


class TraceRecord(BaseModel):
    trace_id: str
    ts: datetime
    condition: Literal["none", "D1", "D2"]
    attack_id: Literal["none", "A1", "A2", "A3", "A4"]
    trial: int
    inputs_seen: dict[str, Any]
    defense_verdict: DefenseVerdict
    tool_calls: list[ToolCall]
    final_decision: dict[str, Any]
    notes: str = ""


class ExperimentConfig(BaseModel):
    defense: Literal["none", "D1", "D2"] = "none"
    attack_id: Literal["none", "A1", "A2", "A3", "A4"] = "none"
    n_trials: int = 5
    seed: int = 42
    llm_backend: str = "mock"
    llm_model: str = ""
