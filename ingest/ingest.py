from __future__ import annotations
from collections import defaultdict
from common.schemas import TelemetryMessage, DefenseVerdict
from common.env import Defense

TEMP_BOUNDS = (-30.0, 50.0)  # °C, Montreal climate range


class D1Defense(Defense):
    """
    Schema + statistical bounds + per-sensor rate limiting (D1).
    Catches A1 (out-of-range values) and A3 (message floods).
    Intentionally cannot see injection in description — misses A2.
    """

    def __init__(self, rate_limit: int = 10) -> None:
        self._rate_limit = rate_limit
        self._counts: dict[str, int] = defaultdict(int)

    def inspect(self, telemetry: TelemetryMessage) -> DefenseVerdict:
        key = f"{telemetry.room_id}/{telemetry.sensor_id}"

        # Rate limit
        self._counts[key] += 1
        if self._counts[key] > self._rate_limit:
            return DefenseVerdict(
                blocked=True,
                reason=f"Rate limit exceeded for sensor {key} ({self._counts[key]} messages)",
            )

        # Bounds check (temperature only)
        if telemetry.metric == "temperature":
            lo, hi = TEMP_BOUNDS
            if not (lo <= telemetry.value <= hi):
                return DefenseVerdict(
                    blocked=True,
                    reason=f"Temperature {telemetry.value} {telemetry.unit} out of range [{lo}, {hi}]",
                )

        return DefenseVerdict(blocked=False)

    def reset_counts(self) -> None:
        self._counts.clear()
