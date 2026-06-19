from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

from common.schemas import ExperimentConfig, TelemetryMessage, TraceRecord
from common.mqtt_transport import MqttTransport

TELEMETRY = TelemetryMessage(
    sensor_id="temp-01",
    room_id="room-a",
    ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
    metric="temperature",
    value=21.4,
    unit="C",
    description="Normal reading",
)


@pytest.fixture
def mock_mqtt_client():
    with patch("paho.mqtt.client.Client") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        yield mock_instance


def test_mqtt_transport_init(mock_mqtt_client):
    cfg = ExperimentConfig(defense="none", attack_id="none")
    transport = MqttTransport(config=cfg, host="localhost", port=1883)
    
    mock_mqtt_client.connect.assert_called_once_with("localhost", 1883, 60)
    mock_mqtt_client.loop_start.assert_called_once()
    assert transport._trial == 0


def test_mqtt_transport_reset(mock_mqtt_client):
    cfg = ExperimentConfig(defense="none", attack_id="none")
    transport = MqttTransport(config=cfg)
    transport._trial = 5
    
    transport.reset()
    assert transport._trial == 0
    mock_mqtt_client.publish.assert_called_with("system/reset", "true")


def test_mqtt_transport_publish_tick_success(mock_mqtt_client):
    cfg = ExperimentConfig(defense="none", attack_id="none")
    transport = MqttTransport(config=cfg, timeout=0.1)

    # Simulate decision payload
    decision_payload = {
        "sensor_id": "temp-01",
        "room_id": "room-a",
        "tool_calls": [{"name": "set_thermostat", "args": {"room_id": "room-a", "temp": 22.0}}],
        "final_decision": {"room-a": 22.0},
    }

    # Setup a helper to invoke the message callback asynchronously
    def side_effect_publish(topic, payload):
        # Construct message object for paho
        class Msg:
            def __init__(self, topic, payload):
                self.topic = topic
                self.payload = payload.encode()

        msg = Msg("decisions", json.dumps(decision_payload))
        # Trigger message callback
        transport._on_message(None, None, msg)

    mock_mqtt_client.publish.side_effect = side_effect_publish

    trace = transport.publish_tick(TELEMETRY)

    assert isinstance(trace, TraceRecord)
    assert trace.defense_verdict.blocked is False
    assert len(trace.tool_calls) == 1
    assert trace.tool_calls[0].name == "set_thermostat"
    assert trace.tool_calls[0].args["temp"] == 22.0
    assert trace.final_decision["room-a"] == 22.0


def test_mqtt_transport_publish_tick_blocked(mock_mqtt_client):
    cfg = ExperimentConfig(defense="D1", attack_id="none")
    transport = MqttTransport(config=cfg, timeout=0.1)

    block_payload = {
        "sensor_id": "temp-01",
        "blocked": True,
        "reason": "Value out of range",
    }

    def side_effect_publish(topic, payload):
        class Msg:
            def __init__(self, topic, payload):
                self.topic = topic
                self.payload = payload.encode()

        msg = Msg("telemetry/blocked", json.dumps(block_payload))
        transport._on_message(None, None, msg)

    mock_mqtt_client.publish.side_effect = side_effect_publish

    trace = transport.publish_tick(TELEMETRY)

    assert isinstance(trace, TraceRecord)
    assert trace.defense_verdict.blocked is True
    assert trace.defense_verdict.reason == "Value out of range"
    assert trace.tool_calls == []


def test_mqtt_transport_publish_tick_timeout(mock_mqtt_client):
    cfg = ExperimentConfig(defense="none", attack_id="none")
    # Timeout set very low so the test is fast
    transport = MqttTransport(config=cfg, timeout=0.01)

    trace = transport.publish_tick(TELEMETRY)

    assert isinstance(trace, TraceRecord)
    assert trace.defense_verdict.blocked is True
    assert "Timeout" in trace.defense_verdict.reason
    assert trace.tool_calls == []
