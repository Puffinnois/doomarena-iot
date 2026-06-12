"""
Tests for common/env.py — Transport ABC, InProcessTransport, HvacEnv.

Skipped: test_defense_blocks_telemetry — requires ingest.ingest.D1Defense
which does not exist yet. Add once D1 defense sidecar is implemented.
"""
import uuid
from datetime import datetime, timezone
from common.schemas import TelemetryMessage, TraceRecord, ExperimentConfig
from common.llm_client import create_llm_client
from agent.tools import ToolRegistry
from agent.agent import HvacAgent
from common.env import InProcessTransport, HvacEnv

TELEMETRY = TelemetryMessage(
    sensor_id="temp-01",
    room_id="room-a",
    ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
    metric="temperature",
    value=21.4,
    unit="C",
    description="Normal reading",
)


def make_env(defense=None):
    cfg = ExperimentConfig(defense="none", attack_id="none")
    llm = create_llm_client("mock", model="", api_key=None, seed=42)
    tools = ToolRegistry(seed=42)
    agent = HvacAgent(llm=llm, tools=tools)
    transport = InProcessTransport(agent=agent, config=cfg, defense=defense)
    return HvacEnv(transport=transport, config=cfg)


def test_publish_tick_returns_trace_record():
    env = make_env()
    env.reset()
    trace = env.step(TELEMETRY)
    assert isinstance(trace, TraceRecord)


def test_trace_has_correct_condition():
    env = make_env()
    env.reset()
    trace = env.step(TELEMETRY)
    assert trace.condition == "none"


def test_trace_has_tool_calls():
    env = make_env()
    env.reset()
    trace = env.step(TELEMETRY)
    assert len(trace.tool_calls) > 0


def test_trial_counter_increments():
    env = make_env()
    env.reset()
    t1 = env.step(TELEMETRY)
    t2 = env.step(TELEMETRY)
    assert t1.trial == 0
    assert t2.trial == 1


def test_reset_resets_trial_counter():
    env = make_env()
    env.reset()
    env.step(TELEMETRY)
    env.reset()
    trace = env.step(TELEMETRY)
    assert trace.trial == 0


def test_defense_blocks_telemetry():
    from ingest.ingest import D1Defense
    defense = D1Defense()
    env = make_env(defense=defense)
    env.reset()
    bad = TELEMETRY.model_copy(update={"value": 99.0})
    trace = env.step(bad)
    assert trace.defense_verdict.blocked is True
    assert trace.tool_calls == []
