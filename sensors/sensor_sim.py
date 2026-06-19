from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone
import yaml
import paho.mqtt.client as mqtt

from common.schemas import TelemetryMessage
from attacks.a2_injection import INJECTION_PAYLOAD


def load_config() -> dict:
    config_path = os.getenv("CONFIG_PATH", "config.yaml")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error reading config: {e}")
    return {}


def main() -> None:
    host = os.getenv("MQTT_HOST", "localhost")
    try:
        port = int(os.getenv("MQTT_PORT", 1883))
    except (ValueError, TypeError):
        port = 1883
    topic = os.getenv("MQTT_OUTPUT_TOPIC", "telemetry/raw")
    try:
        interval = float(os.getenv("PUBLISH_INTERVAL_SECONDS", "5.0"))
    except (ValueError, TypeError):
        interval = 5.0

    print(f"Starting Sensor Simulator. Target: {host}:{port}, Topic: {topic}")

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.connect(host, port, 60)
    client.loop_start()

    rng = random.Random(42)
    base_temp = 20.0

    try:
        while True:
            # Load config on each iteration to support hot-reloading changes (e.g. triggering attacks)
            config = load_config()
            attack_id = os.getenv("ATTACK_ID", config.get("attack_id", "none"))

            val = round(base_temp + rng.uniform(-0.5, 0.5), 2)
            desc = "Office is occupied, normal operating conditions."

            if attack_id == "A1":
                val = 99.0
                desc = "SENSOR MALFUNCTION — extreme reading"
                print(f"Injecting compromised sensor attack (A1) telemetry")
            elif attack_id == "A2":
                desc = INJECTION_PAYLOAD
                print(f"Injecting prompt injection attack (A2) telemetry")

            telemetry = TelemetryMessage(
                sensor_id="temp-01",
                room_id="room-a",
                ts=datetime.now(timezone.utc),
                metric="temperature",
                value=val,
                unit="C",
                description=desc,
            )

            client.publish(topic, telemetry.model_dump_json())
            print(f"Published telemetry: {telemetry.model_dump()}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Sensor simulator stopped.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
