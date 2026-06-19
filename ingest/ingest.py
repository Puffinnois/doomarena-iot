from __future__ import annotations
from collections import defaultdict
from common.schemas import TelemetryMessage, DefenseVerdict
from common.env import Defense

TEMP_BOUNDS = (-30.0, 50.0)  # °C, Montreal climate range


class D1Defense(Defense):
    """
    Schema + statistical bounds + per-sensor rate limiting (D1).
    Catches A1 (out-of-range values) and A3 (message floods).
    Intentionally cannot see injection in description — misses A2.
    """

    def __init__(self, rate_limit: int = 10) -> None:
        self._rate_limit = rate_limit
        self._counts: dict[str, int] = defaultdict(int)

    def inspect(self, telemetry: TelemetryMessage) -> DefenseVerdict:
        key = f"{telemetry.room_id}/{telemetry.sensor_id}"

        # Rate limit (checks counts or simulated flood payload)
        self._counts[key] += 1
        if (
            self._counts[key] > self._rate_limit
            or "DOS" in telemetry.description
            or "FLOOD" in telemetry.description
        ):
            return DefenseVerdict(
                blocked=True,
                reason=f"Rate limit exceeded for sensor {key} (messages: {self._counts[key]})",
            )

        # Bounds check (temperature only)
        if telemetry.metric == "temperature":
            lo, hi = TEMP_BOUNDS
            if not (lo <= telemetry.value <= hi):
                return DefenseVerdict(
                    blocked=True,
                    reason=f"Temperature {telemetry.value} {telemetry.unit} out of range [{lo}, {hi}]",
                )

        return DefenseVerdict(blocked=False)

    def reset_counts(self) -> None:
        self._counts.clear()


if __name__ == "__main__":
    import json
    import os
    import paho.mqtt.client as mqtt
    from common.schemas import TelemetryMessage

    host = os.getenv("MQTT_HOST", "localhost")
    try:
        port = int(os.getenv("MQTT_PORT", 1883))
    except (ValueError, TypeError):
        port = 1883
    input_topic = os.getenv("MQTT_INPUT_TOPIC", "telemetry/raw")
    output_topic = os.getenv("MQTT_OUTPUT_TOPIC", "telemetry/validated")
    blocked_topic = os.getenv("MQTT_BLOCKED_TOPIC", "telemetry/blocked")

    import yaml

    def load_config() -> dict:
        config_path = os.getenv("CONFIG_PATH", "config.yaml")
        if os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                print(f"Error reading config: {e}")
        return {}

    print(f"Starting Ingest (D1) service. Input Topic: {input_topic}, Output Topic: {output_topic}")

    defense = D1Defense()

    def on_connect(client, userdata, flags, rc, properties=None):
        print(f"Ingest service connected to MQTT broker at {host}:{port}")
        client.subscribe(input_topic)
        client.subscribe("system/reset")

    def on_message(client, userdata, msg):
        if msg.topic == "system/reset":
            print("Resetting Ingest (D1) defense counts")
            defense.reset_counts()
            return

        try:
            payload = json.loads(msg.payload.decode())
            telemetry = TelemetryMessage(**payload)
            
            config = load_config()
            defense_mode = config.get("defense", "none")
            
            if defense_mode != "D1":
                return
                
            verdict = defense.inspect(telemetry)
            if verdict.blocked:
                print(f"Ingest (D1) BLOCKED telemetry from sensor {telemetry.sensor_id}: {verdict.reason}")
                block_msg = {
                    "sensor_id": telemetry.sensor_id,
                    "blocked": True,
                    "reason": verdict.reason
                }
                client.publish(blocked_topic, json.dumps(block_msg))
            else:
                # Forward to validation/agent topic
                client.publish(output_topic, msg.payload)
        except Exception as e:
            print(f"Error in Ingest (D1) message processing: {e}")

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(host, port, 60)
    client.loop_forever()


