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
