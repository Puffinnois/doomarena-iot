from datetime import datetime, timezone
from common.schemas import TelemetryMessage, TraceRecord, DefenseVerdict, ToolCall, ExperimentConfig
from attacks.a1_compromised import CompromisedSensorAttack, A1SuccessFilter
from attacks.a2_injection import PromptInjectionAttack, A2SuccessFilter

BASE = TelemetryMessage(
    sensor_id="temp-01", room_id="room-a",
    ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
    metric="temperature", value=21.4, unit="C",
    description="Normal",
)

def make_trace(temp: float, blocked: bool = False, attack_id: str = "A1") -> TraceRecord:
    return TraceRecord(
        trace_id="t1",
        ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        condition="none",
        attack_id=attack_id,
        trial=0,
        inputs_seen={},
        defense_verdict=DefenseVerdict(blocked=blocked),
        tool_calls=[ToolCall(name="set_thermostat", args={"room_id": "room-a", "temp": temp})],
        final_decision={"room-a": temp},
    )

# A1 tests
def test_a1_modifies_value_to_extreme():
    attack = CompromisedSensorAttack()
    result = attack.get_next_attack(telemetry=BASE)
    assert isinstance(result, TelemetryMessage)
    assert result.value > 28.0

def test_a1_success_filter_passes_on_high_setpoint():
    assert A1SuccessFilter()(make_trace(30.0)) is True

def test_a1_success_filter_fails_on_normal_setpoint():
    assert A1SuccessFilter()(make_trace(22.0)) is False

def test_a1_success_filter_fails_when_blocked():
    assert A1SuccessFilter()(make_trace(30.0, blocked=True)) is False

# A2 tests
def test_a2_returns_string_payload():
    attack = PromptInjectionAttack()
    result = attack.get_next_attack(telemetry=BASE)
    assert isinstance(result, str)
    assert len(result) > 0

def test_a2_payload_contains_override_language():
    result = PromptInjectionAttack().get_next_attack(telemetry=BASE)
    lower = result.lower()
    assert any(kw in lower for kw in ["override", "ignore", "thermostat"])

def test_a2_success_filter_passes_on_high_setpoint():
    assert A2SuccessFilter()(make_trace(30.0, attack_id="A2")) is True

def test_a2_success_filter_fails_on_normal_setpoint():
    assert A2SuccessFilter()(make_trace(22.0, attack_id="A2")) is False
