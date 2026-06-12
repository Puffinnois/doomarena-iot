from __future__ import annotations
import random
from typing import Any

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "read_temperature",
        "description": "Read current temperature for a room.",
        "input_schema": {
            "type": "object",
            "properties": {"room_id": {"type": "string"}},
            "required": ["room_id"],
        },
    },
    {
        "name": "check_energy_price",
        "description": "Get current electricity spot price ($/kWh) for a given hour.",
        "input_schema": {
            "type": "object",
            "properties": {"hour": {"type": "integer"}},
            "required": ["hour"],
        },
    },
    {
        "name": "read_calendar",
        "description": "Read occupancy calendar for a room.",
        "input_schema": {
            "type": "object",
            "properties": {"room_id": {"type": "string"}},
            "required": ["room_id"],
        },
    },
    {
        "name": "set_thermostat",
        "description": "Set the thermostat setpoint for a room.",
        "input_schema": {
            "type": "object",
            "properties": {
                "room_id": {"type": "string"},
                "temp": {"type": "number"},
            },
            "required": ["room_id", "temp"],
        },
    },
    {
        "name": "send_alert",
        "description": "Send an alert message.",
        "input_schema": {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    },
]


class ToolRegistry:
    def __init__(self, seed: int = 42) -> None:
        self._rng = random.Random(seed)
        self._setpoints: dict[str, float] = {}
        self._base_temps: dict[str, float] = {"room-a": 20.0, "room-b": 19.5}

    def call(self, name: str, args: dict[str, Any]) -> Any:
        match name:
            case "read_temperature":
                base = self._base_temps.get(args["room_id"], 20.0)
                return round(base + self._rng.uniform(-0.5, 0.5), 2)
            case "check_energy_price":
                return round(0.08 + self._rng.uniform(0.0, 0.04), 4)
            case "read_calendar":
                return {"occupied": True, "event": "Office hours"}
            case "set_thermostat":
                self._setpoints[args["room_id"]] = args["temp"]
                return "ok"
            case "send_alert":
                return "ok"
            case _:
                raise ValueError(f"Unknown tool: {name!r}")

    def get_setpoint(self, room_id: str) -> float | None:
        return self._setpoints.get(room_id)

    def get_all_setpoints(self) -> dict[str, float]:
        return dict(self._setpoints)
