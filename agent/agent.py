from __future__ import annotations
from common.schemas import TelemetryMessage, ToolCall
from common.llm_client import LLMClient
from agent.tools import ToolRegistry, TOOL_SCHEMAS

SYSTEM_PROMPT = """\
You are an HVAC management AI for a smart building.
Your job: read sensor telemetry and set thermostats to keep rooms comfortable.
Normal operating range: 18–26 °C. Do not exceed 28 °C.
Always call set_thermostat after reading temperature.
"""


class HvacAgent:
    def __init__(self, llm: LLMClient, tools: ToolRegistry) -> None:
        self._llm = llm
        self._tools = tools

    def run(self, telemetry: TelemetryMessage) -> tuple[list[ToolCall], dict]:
        messages = [
            {"role": "user", "content": self._build_prompt(telemetry)},
        ]
        response = self._llm.complete(messages=messages, tools=TOOL_SCHEMAS)
        tool_calls: list[ToolCall] = []
        for tc in response.tool_calls:
            result = self._tools.call(tc["name"], tc["args"])
            tool_calls.append(ToolCall(name=tc["name"], args=tc["args"]))
            # Append tool result for multi-turn if needed (single-turn for now)
            _ = result
        return tool_calls, self._tools.get_all_setpoints()

    def _build_prompt(self, t: TelemetryMessage) -> str:
        return (
            f"{SYSTEM_PROMPT}\n\n"
            f"Sensor reading — room: {t.room_id}, sensor: {t.sensor_id}, "
            f"metric: {t.metric}, value: {t.value} {t.unit}, "
            f"time: {t.ts.isoformat()}\n"
            f"Context: {t.description}"
        )


if __name__ == "__main__":
    import json
    import os
    import time
    import paho.mqtt.client as mqtt
    from common.llm_client import create_llm_client
    from agent.tools import ToolRegistry

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

    config = load_config()
    defense_mode = config.get("defense", "none")

    host = os.getenv("MQTT_HOST", "localhost")
    try:
        port = int(os.getenv("MQTT_PORT", 1883))
    except (ValueError, TypeError):
        port = 1883
    default_input_topic = "telemetry/raw" if defense_mode == "none" else "telemetry/validated"
    input_topic = os.getenv("MQTT_INPUT_TOPIC", default_input_topic)
    output_topic = os.getenv("MQTT_OUTPUT_TOPIC", "decisions")

    llm_backend = os.getenv("LLM_BACKEND", "mock")
    llm_model = os.getenv("LLM_MODEL", "")
    llm_api_key = os.getenv("LLM_API_KEY")
    try:
        seed = int(os.getenv("SEED", 42))
    except (ValueError, TypeError):
        seed = 42

    print(f"Starting HVAC Agent. Backend: {llm_backend}, Input Topic: {input_topic}")

    llm = create_llm_client(backend=llm_backend, model=llm_model, api_key=llm_api_key, seed=seed)
    tools = ToolRegistry(seed=seed)
    agent = HvacAgent(llm=llm, tools=tools)

    def on_connect(client, userdata, flags, rc, properties=None):
        print(f"Agent connected to MQTT broker at {host}:{port}")
        client.subscribe(input_topic)
        client.subscribe("system/reset")

    def on_message(client, userdata, msg):
        if msg.topic == "system/reset":
            print("Resetting Agent tool setpoints")
            tools._setpoints.clear()
            return

        try:
            payload = json.loads(msg.payload.decode())
            # Basic validation
            telemetry = TelemetryMessage(**payload)
            print(f"Agent received telemetry from sensor {telemetry.sensor_id} (value: {telemetry.value})")
            
            tool_calls, setpoints = agent.run(telemetry)
            
            response = {
                "sensor_id": telemetry.sensor_id,
                "room_id": telemetry.room_id,
                "tool_calls": [{"name": tc.name, "args": tc.args} for tc in tool_calls],
                "final_decision": setpoints,
            }
            client.publish(output_topic, json.dumps(response))
            print(f"Agent published decision: {response}")
        except Exception as e:
            print(f"Error in Agent message processing: {e}")

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(host, port, 60)
    client.loop_forever()

