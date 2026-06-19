from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

from common.schemas import DefenseVerdict, ExperimentConfig, TelemetryMessage, TraceRecord, ToolCall
from common.env import Transport

logger = logging.getLogger(__name__)


class MqttTransport(Transport):
    """Live MQTT backend connecting to an external Mosquitto broker."""

    def __init__(
        self,
        config: ExperimentConfig,
        host: str | None = None,
        port: int | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._config = config
        self._host = host or os.getenv("MQTT_HOST", "localhost")
        try:
            self._port = int(port or os.getenv("MQTT_PORT", 1883))
        except (ValueError, TypeError):
            self._port = 1883
        self._timeout = timeout
        self._trial = 0

        # Use CallbackAPIVersion.VERSION2 for compatibility with paho-mqtt>=2.0
        self._client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_message = self._on_message
        self._client.on_connect = self._on_connect

        self._response_event = threading.Event()
        self._response_data: dict | None = None
        self._current_sensor_id: str | None = None

        self._client.connect(self._host, self._port, 60)
        self._client.loop_start()

    def _on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        client.subscribe("decisions")
        client.subscribe("telemetry/blocked")

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload.decode())
            sensor_id = payload.get("sensor_id")
            if sensor_id == self._current_sensor_id:
                self._response_data = {
                    "topic": msg.topic,
                    "payload": payload,
                }
                self._response_event.set()
        except Exception as e:
            logger.error(f"Error parsing MQTT message: {e}")

    def reset(self) -> None:
        self._trial = 0
        # Publish reset to clean state / rate limits in services
        self._client.publish("system/reset", "true")

    def publish_tick(self, telemetry: TelemetryMessage) -> TraceRecord:
        self._current_sensor_id = telemetry.sensor_id
        self._response_event.clear()
        self._response_data = None

        # Publish the telemetry message to telemetry/raw
        self._client.publish("telemetry/raw", telemetry.model_dump_json())

        # Wait for either a decision or a blocked message
        success = self._response_event.wait(timeout=self._timeout)

        verdict = DefenseVerdict(blocked=False)
        tool_calls: list[ToolCall] = []
        final_decision: dict = {}

        if not success:
            logger.warning(f"Timeout waiting for response for sensor {telemetry.sensor_id}")
            verdict = DefenseVerdict(blocked=True, reason="Timeout waiting for MQTT response")
        else:
            topic = self._response_data["topic"]
            payload = self._response_data["payload"]
            if topic == "telemetry/blocked":
                verdict = DefenseVerdict(
                    blocked=True,
                    reason=payload.get("reason", "Blocked by defense")
                )
            elif topic == "decisions":
                for tc in payload.get("tool_calls", []):
                    tool_calls.append(ToolCall(name=tc["name"], args=tc["args"]))
                final_decision = payload.get("final_decision", {})

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

    def __del__(self) -> None:
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:
            pass
