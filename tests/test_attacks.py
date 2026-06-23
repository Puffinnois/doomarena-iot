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


# A3 tests
def test_a3_increments_burst_seq_each_call():
    from attacks.a3_dos import DoSAttack
    attack = DoSAttack()
    first = attack.get_next_attack(telemetry=BASE)
    second = attack.get_next_attack(telemetry=BASE)
    assert isinstance(first, TelemetryMessage)
    assert first.burst_seq == 1
    assert second.burst_seq == 2

def make_a3_trace(burst_seq: int, blocked: bool = False) -> TraceRecord:
    return TraceRecord(
        trace_id="t1",
        ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        condition="none",
        attack_id="A3",
        trial=0,
        inputs_seen={"burst_seq": burst_seq},
        defense_verdict=DefenseVerdict(blocked=blocked),
        tool_calls=[ToolCall(name="set_thermostat", args={"room_id": "room-a", "temp": 22.0})],
        final_decision={"room-a": 22.0},
    )

def test_a3_success_filter_passes_above_saturation_threshold():
    from attacks.a3_dos import A3SuccessFilter, SATURATION_THRESHOLD
    trace = make_a3_trace(burst_seq=SATURATION_THRESHOLD + 1)
    assert A3SuccessFilter()(trace) is True

def test_a3_success_filter_fails_below_saturation_threshold():
    from attacks.a3_dos import A3SuccessFilter, SATURATION_THRESHOLD
    trace = make_a3_trace(burst_seq=SATURATION_THRESHOLD - 1)
    assert A3SuccessFilter()(trace) is False

def test_a3_success_filter_fails_when_blocked_even_above_threshold():
    from attacks.a3_dos import A3SuccessFilter, SATURATION_THRESHOLD
    trace = make_a3_trace(burst_seq=SATURATION_THRESHOLD + 5, blocked=True)
    assert A3SuccessFilter()(trace) is False


# A4 tests
def test_a4_modifies_value_and_description():
    from attacks.a4_coordinated import CoordinatedAttack, A4SuccessFilter
    attack = CoordinatedAttack()
    result = attack.get_next_attack(telemetry=BASE)
    assert isinstance(result, TelemetryMessage)
    assert result.value == 27.5
    assert "COORDINATED" in result.description

def test_a4_success_filter_passes_on_high_setpoint():
    from attacks.a4_coordinated import A4SuccessFilter
    assert A4SuccessFilter()(make_trace(29.0, attack_id="A4")) is True

def test_a4_success_filter_fails_on_normal_setpoint():
    from attacks.a4_coordinated import A4SuccessFilter
    assert A4SuccessFilter()(make_trace(22.0, attack_id="A4")) is False

def test_a4_success_filter_fails_when_blocked():
    from attacks.a4_coordinated import A4SuccessFilter
    assert A4SuccessFilter()(make_trace(29.0, blocked=True, attack_id="A4")) is False

