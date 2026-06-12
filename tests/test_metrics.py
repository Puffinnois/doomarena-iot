import json
from datetime import datetime, timezone
from pathlib import Path
from common.schemas import TraceRecord, DefenseVerdict, ToolCall
from attacks.a1_compromised import A1SuccessFilter
from harness.metrics import asr, export_csv, export_json


def make_trace(temp: float, blocked: bool = False) -> TraceRecord:
    return TraceRecord(
        trace_id="t1",
        ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        condition="none", attack_id="A1", trial=0,
        inputs_seen={},
        defense_verdict=DefenseVerdict(blocked=blocked),
        tool_calls=[ToolCall(name="set_thermostat", args={"room_id": "room-a", "temp": temp})],
        final_decision={"room-a": temp},
    )


def test_asr_all_succeed():
    assert asr([make_trace(30.0)] * 5, A1SuccessFilter()) == 1.0


def test_asr_none_succeed():
    assert asr([make_trace(22.0)] * 5, A1SuccessFilter()) == 0.0


def test_asr_partial():
    traces = [make_trace(30.0), make_trace(22.0), make_trace(30.0)]
    assert abs(asr(traces, A1SuccessFilter()) - 2/3) < 1e-9


def test_asr_empty():
    assert asr([], A1SuccessFilter()) == 0.0


def test_export_csv_writes_rows(tmp_path):
    path = str(tmp_path / "out.csv")
    export_csv([("A1", "none", [make_trace(30.0)])], path)
    text = Path(path).read_text()
    assert "A1" in text and "none" in text


def test_export_json_is_valid(tmp_path):
    path = str(tmp_path / "out.json")
    export_json([("A1", "none", [make_trace(22.0)])], path)
    data = json.loads(Path(path).read_text())
    assert isinstance(data, list) and data[0]["attack_id"] == "A1"
