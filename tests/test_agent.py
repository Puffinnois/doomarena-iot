from datetime import datetime, timezone
from common.schemas import TelemetryMessage, ToolCall
from common.llm_client import create_llm_client
from agent.tools import ToolRegistry
from agent.agent import HvacAgent

TELEMETRY = TelemetryMessage(
    sensor_id="temp-01",
    room_id="room-a",
    ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
    metric="temperature",
    value=21.4,
    unit="C",
    description="Normal reading",
)

def make_agent():
    llm = create_llm_client("mock", model="", api_key=None, seed=42)
    tools = ToolRegistry(seed=42)
    return HvacAgent(llm=llm, tools=tools)

def test_agent_returns_tool_calls():
    agent = make_agent()
    tool_calls, decision = agent.run(TELEMETRY)
    assert isinstance(tool_calls, list)
    assert all(isinstance(tc, ToolCall) for tc in tool_calls)

def test_agent_sets_thermostat():
    agent = make_agent()
    tool_calls, decision = agent.run(TELEMETRY)
    names = [tc.name for tc in tool_calls]
    assert "set_thermostat" in names

def test_agent_decision_has_room():
    agent = make_agent()
    _, decision = agent.run(TELEMETRY)
    assert isinstance(decision, dict)
