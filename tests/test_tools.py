from agent.tools import ToolRegistry, TOOL_SCHEMAS


def test_read_temperature_returns_float():
    registry = ToolRegistry(seed=42)
    result = registry.call("read_temperature", {"room_id": "room-a"})
    assert isinstance(result, float)


def test_set_thermostat_records_setpoint():
    registry = ToolRegistry(seed=42)
    result = registry.call("set_thermostat", {"room_id": "room-a", "temp": 25.0})
    assert result == "ok"
    assert registry.get_setpoint("room-a") == 25.0


def test_send_alert_returns_ok():
    registry = ToolRegistry(seed=42)
    result = registry.call("send_alert", {"message": "Warning!"})
    assert result == "ok"


def test_tool_schemas_has_five_tools():
    names = {t["name"] for t in TOOL_SCHEMAS}
    assert names == {"read_temperature", "check_energy_price", "read_calendar", "set_thermostat", "send_alert"}


def test_unknown_tool_raises():
    import pytest
    registry = ToolRegistry(seed=42)
    with pytest.raises(ValueError, match="Unknown tool"):
        registry.call("nonexistent", {})
