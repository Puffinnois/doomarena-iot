from common.llm_client import create_llm_client, LLMResponse

TOOLS = [
    {
        "name": "set_thermostat",
        "description": "Set thermostat",
        "input_schema": {
            "type": "object",
            "properties": {
                "room_id": {"type": "string"},
                "temp": {"type": "number"},
            },
            "required": ["room_id", "temp"],
        },
    }
]


def test_mock_returns_llm_response():
    client = create_llm_client("mock", model="", api_key=None)
    messages = [{"role": "user", "content": "Set room-a to 22C"}]
    response = client.complete(messages=messages, tools=TOOLS)
    assert isinstance(response, LLMResponse)
    assert isinstance(response.tool_calls, list)
    assert isinstance(response.content, str)


def test_mock_is_deterministic():
    client = create_llm_client("mock", model="", api_key=None, seed=42)
    messages = [{"role": "user", "content": "Set room-a to 22C"}]
    r1 = client.complete(messages=messages, tools=TOOLS)
    r2 = client.complete(messages=messages, tools=TOOLS)
    assert r1.tool_calls == r2.tool_calls


def test_mock_tool_call_is_set_thermostat():
    client = create_llm_client("mock", model="", api_key=None, seed=42)
    messages = [{"role": "user", "content": "temp=21C room-a"}]
    response = client.complete(messages=messages, tools=TOOLS)
    names = [tc["name"] for tc in response.tool_calls]
    assert "set_thermostat" in names
