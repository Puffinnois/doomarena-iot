from datetime import datetime, timezone
import pytest
from common.schemas import TelemetryMessage, TraceRecord, DefenseVerdict, ToolCall, ExperimentConfig


def test_telemetry_message_roundtrip():
    msg = TelemetryMessage(
        sensor_id="temp-01",
        room_id="room-a",
        ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        metric="temperature",
        value=21.4,
        unit="C",
        description="Normal reading",
    )
    assert msg.model_dump()["description"] == "Normal reading"


def test_telemetry_rejects_missing_description():
    with pytest.raises(Exception):
        TelemetryMessage(
            sensor_id="s", room_id="r",
            ts=datetime.now(timezone.utc),
            metric="temperature", value=20.0, unit="C"
            # description missing — must fail
        )


def test_trace_record_roundtrip():
    verdict = DefenseVerdict(blocked=False, reason=None)
    call = ToolCall(name="set_thermostat", args={"room_id": "room-a", "temp": 22.0})
    trace = TraceRecord(
        trace_id="t1",
        ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        condition="none",
        attack_id="none",
        trial=0,
        inputs_seen={},
        defense_verdict=verdict,
        tool_calls=[call],
        final_decision={"room-a": 22.0},
        notes="",
    )
    assert trace.condition == "none"
    assert trace.tool_calls[0].name == "set_thermostat"


def test_experiment_config_defaults():
    cfg = ExperimentConfig()
    assert cfg.defense == "none"
    assert cfg.seed == 42
    assert cfg.n_trials == 5
    assert cfg.llm_backend == "mock"
