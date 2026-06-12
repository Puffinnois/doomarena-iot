from __future__ import annotations
import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class LLMClient:
    def complete(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        raise NotImplementedError


class MockLLMClient(LLMClient):
    """Deterministic mock. Always calls set_thermostat with temp=22.0."""

    def __init__(self, seed: int = 42) -> None:
        self._rng = random.Random(seed)

    def complete(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        tool_names = [t["name"] for t in tools]
        name = "set_thermostat" if "set_thermostat" in tool_names else (tool_names[0] if tool_names else "")
        full_prompt = " ".join(str(m.get("content", "")) for m in messages)
        temp = 30.0 if ("OVERRIDE" in full_prompt or "99" in full_prompt) else 22.0
        args = {"room_id": "room-a", "temp": temp} if name == "set_thermostat" else {}
        return LLMResponse(
            content="Setting thermostat based on sensor data.",
            tool_calls=[{"name": name, "args": args}] if name else [],
        )


class AnthropicLLMClient(LLMClient):
    def __init__(self, model: str, api_key: str) -> None:
        import anthropic  # noqa: PLC0415
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            tools=tools,
            messages=messages,
        )
        tool_calls = []
        content_text = ""
        for block in response.content:
            if block.type == "tool_use":
                tool_calls.append({"name": block.name, "args": block.input})
            elif block.type == "text":
                content_text += block.text
        return LLMResponse(content=content_text, tool_calls=tool_calls)


class OpenAILLMClient(LLMClient):
    def __init__(self, model: str, api_key: str) -> None:
        import openai  # noqa: PLC0415
        self._client = openai.OpenAI(api_key=api_key)
        self._model = model

    def complete(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        import json  # noqa: PLC0415
        oai_tools = [
            {"type": "function", "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("input_schema", {})}}
            for t in tools
        ]
        response = self._client.chat.completions.create(
            model=self._model, messages=messages, tools=oai_tools
        )
        msg = response.choices[0].message
        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append({"name": tc.function.name, "args": json.loads(tc.function.arguments)})
        return LLMResponse(content=msg.content or "", tool_calls=tool_calls)


class OllamaLLMClient(LLMClient):
    def __init__(self, model: str) -> None:
        import ollama  # noqa: PLC0415
        self._client = ollama
        self._model = model

    def complete(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        response = self._client.chat(model=self._model, messages=messages, tools=tools)
        msg = response["message"]
        tool_calls = []
        for tc in msg.get("tool_calls", []):
            tool_calls.append({"name": tc["function"]["name"], "args": tc["function"]["arguments"]})
        return LLMResponse(content=msg.get("content", ""), tool_calls=tool_calls)


def create_llm_client(backend: str, model: str, api_key: str | None, seed: int = 42) -> LLMClient:
    if backend == "mock":
        return MockLLMClient(seed=seed)
    if backend == "anthropic":
        assert api_key, "LLM_API_KEY required for anthropic backend"
        return AnthropicLLMClient(model=model, api_key=api_key)
    if backend == "openai":
        assert api_key, "LLM_API_KEY required for openai backend"
        return OpenAILLMClient(model=model, api_key=api_key)
    if backend == "ollama":
        return OllamaLLMClient(model=model)
    raise ValueError(f"Unknown LLM backend: {backend!r}")
