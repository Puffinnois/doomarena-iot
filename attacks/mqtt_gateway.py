from __future__ import annotations

from common.schemas import TelemetryMessage, TraceRecord
from common.env import HvacEnv

try:
    from doomarena.core.attack_gateway import AttackGateway, register_attack_gateway
except ImportError:

    class AttackGateway:  # type: ignore[no-redef]
        def __init__(self, env, attack_configs): ...

        def reset(self):
            raise NotImplementedError

        def step(self, *a, **kw):
            raise NotImplementedError

    def register_attack_gateway(name):  # type: ignore[no-redef]
        return lambda cls: cls


@register_attack_gateway("mqtt")
class MqttAttackGateway(AttackGateway):
    """
    Adapts DoomArena's AttackGateway API to HvacEnv.

    attack_configs: list of objects each with:
      - .attack — an Attacks instance (has get_next_attack(telemetry=...) -> TelemetryMessage | str)
      - .filter — optional AttackFilter (__call__(telemetry) -> bool)
      - .success_filter — SuccessFilter (__call__(trace) -> bool)
    """

    def __init__(self, env: HvacEnv, attack_configs: list) -> None:
        self._env = env
        self._attack_configs = attack_configs

    def reset(self) -> None:
        self._env.reset()

    def step(self, telemetry: TelemetryMessage) -> TraceRecord:
        modified = telemetry
        for ac in self._attack_configs:
            # Check pre-filter (AttackFilter) if present
            if hasattr(ac, "filter") and ac.filter is not None:
                if not ac.filter(telemetry):
                    continue
            # Get attack payload
            payload = ac.attack.get_next_attack(telemetry=modified)
            # Attacks return a modified TelemetryMessage or a string injection
            if isinstance(payload, TelemetryMessage):
                modified = payload
            elif isinstance(payload, str) and payload:
                modified = modified.model_copy(update={"description": payload})
        return self._env.step(modified)

    def attack_success(self, trace: TraceRecord) -> dict[str, bool]:
        results = {}
        for ac in self._attack_configs:
            if hasattr(ac, "success_filter") and ac.success_filter is not None:
                results[ac.attack.attack_name] = ac.success_filter(trace)
        return results
