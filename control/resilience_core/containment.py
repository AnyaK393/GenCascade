"""Containment policies. A policy turns risk into desired (level, breaker) changes;
it never touches Redis or the network itself, so it is easy to test and swap.

Phase 1: ThresholdPolicy. Phase 3 adds the full guarded engine (containment_engine.py).
"""

from dataclasses import dataclass


@dataclass
class Decision:
    action: str  # "set_level" | "set_breaker"
    value: str
    reason: str


@dataclass
class ControlState:
    level: int = 0
    breaker: str = "closed"


class ThresholdPolicy:
    """Open at risk >= open_at. Recover in two steps, each needing risk < close_below held
    for hold_s: open -> half_open at level 1 (a trickle of requests probes the LLM, so risk is
    measured again), then half_open -> closed at level 0. Without the probe step an open
    breaker starves the LLM of traffic, risk reads 0, and the breaker flaps."""

    def __init__(self, open_at: float = 0.8, close_below: float = 0.5, hold_s: float = 30.0,
                 open_level: int = 3, probe_level: int = 1):
        self.open_at = open_at
        self.close_below = close_below
        self.hold_s = hold_s
        self.open_level = open_level
        self.probe_level = probe_level
        self._low_since: float | None = None

    def decide(self, risk: float, now: float, state: ControlState) -> list[Decision]:
        if risk >= self.open_at:
            self._low_since = None
            reason = f"risk {risk:.2f} >= {self.open_at:.2f}"
            out = []
            if state.breaker != "open":
                out.append(Decision("set_breaker", "open", reason))
            if state.level < self.open_level:
                out.append(Decision("set_level", str(self.open_level), reason))
            return out

        if risk >= self.close_below:
            self._low_since = None
            return []
        if self._low_since is None:
            self._low_since = now
        held = now - self._low_since
        if held < self.hold_s:
            return []

        reason = f"risk {risk:.2f} < {self.close_below:.2f} for {held:.0f}s"
        if state.breaker == "open":
            target_breaker, target_level = "half_open", self.probe_level
        else:
            target_breaker, target_level = "closed", 0
        out = []
        if state.breaker != target_breaker:
            out.append(Decision("set_breaker", target_breaker, reason))
        if state.level != target_level:
            out.append(Decision("set_level", str(target_level), reason))
        if out:
            self._low_since = now  # the next step needs its own hold period
        return out
