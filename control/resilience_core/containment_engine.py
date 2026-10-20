"""Containment engine (guide 6.5): a small policy with guardrails, not raw model output.

| Condition (LLM cascade risk R)                       | Action                               |
| R >= 0.6 for 6 s                                      | level 1 (lean)                       |
| R >= threshold for 4 s                                | breaker open, level >= 2             |
| breaker open and R still rising after 30 s            | level 3 (hints)                      |
| admission limit at minimum and queue still growing    | level 4 (shed)                       |
| R < 0.5 held for 30 s                                 | step down one notch (see below)      |

Step-down sequence, one notch per calm period: 4 -> 3 -> 2, then (2, open) -> (1, half-open)
-> (1, closed) -> (0, closed). Guardrails: at most one change per 10 s, except the jump to an open
breaker; every step down needs its own 30 s of calm, which is also the cooldown.

The engine is pure: it reads an Observation and returns Decisions. The core applies them (or
logs them in dry-run, or queues them for approval) and owns the kill switch.
"""

from collections import deque
from dataclasses import dataclass, field


@dataclass
class EngineConfig:
    threshold: float = 0.8
    lean_at: float = 0.6
    lean_hold_s: float = 6
    open_hold_s: float = 4
    rising_after_s: float = 30
    calm_below: float = 0.5
    calm_hold_s: float = 30
    min_gap_s: float = 10
    admission_min: int = 1


@dataclass
class Observation:
    now: float
    risk: float | None  # LLM cascade risk; None = no fresh prediction
    level: int  # level Fedora last requested (the platform may apply a higher floor)
    breaker: str  # breaker Fedora last requested
    queue_growth_per_s: float = 0.0
    admission_limit: int | None = None  # gateway AIMD limit, only during an exam


@dataclass
class Decision:
    action: str  # set_level | set_breaker
    value: str
    reason: str


@dataclass
class ContainmentEngine:
    cfg: EngineConfig = field(default_factory=EngineConfig)

    def __post_init__(self):
        self.history: deque[tuple[float, float]] = deque(maxlen=120)
        self.last_change = float("-inf")
        self.opened_at: float | None = None

    def _held(self, now: float, pred, seconds: float) -> bool:
        """pred(risk) true for every sample in the last `seconds` (and the history covers it)."""
        if not self.history or now - self.history[0][0] < seconds:
            return False
        return all(pred(r) for t, r in self.history if t >= now - seconds)

    def _risk_ago(self, now: float, seconds: float) -> float | None:
        older = [r for t, r in self.history if t <= now - seconds]
        return older[-1] if older else None

    def _calm_for(self, now: float) -> float:
        """Seconds of uninterrupted calm, counted from the last change at the earliest."""
        start = now
        for t, r in reversed(self.history):
            if r >= self.cfg.calm_below or t < self.last_change:
                break
            start = t
        return now - start

    def decide(self, obs: Observation) -> list[Decision]:
        if obs.risk is None:
            return []
        c, now, R = self.cfg, obs.now, obs.risk
        self.history.append((now, R))
        level, breaker = obs.level, obs.breaker
        out: list[Decision] = []

        # Breach: straight to an open breaker and cache + RAG; allowed inside the 10 s gap.
        if self._held(now, lambda r: r >= c.threshold, c.open_hold_s) and (breaker != "open" or level < 2):
            reason = f"risk {R:.2f} >= {c.threshold:.2f} for {c.open_hold_s:.0f}s"
            if breaker != "open":
                out.append(Decision("set_breaker", "open", reason))
                self.opened_at = now
            if level < 2:
                out.append(Decision("set_level", "2", reason))
            self.last_change = now
            return out

        if now - self.last_change < c.min_gap_s:
            return []

        if breaker == "open" and level == 2 and self.opened_at is not None \
                and now - self.opened_at >= c.rising_after_s:
            before = self._risk_ago(now, c.rising_after_s)
            if before is not None and R > before and R >= c.threshold:
                out.append(Decision("set_level", "3", f"breaker open {now - self.opened_at:.0f}s and risk "
                                                      f"still rising ({before:.2f} -> {R:.2f})"))
        elif level == 3 and obs.admission_limit is not None and obs.admission_limit <= c.admission_min \
                and obs.queue_growth_per_s > 0:
            out.append(Decision("set_level", "4", f"admission limit at minimum ({obs.admission_limit}) and "
                                                  f"queue growing {obs.queue_growth_per_s:.2f}/s"))
        elif level < 1 and self._held(now, lambda r: r >= c.lean_at, c.lean_hold_s):
            out.append(Decision("set_level", "1", f"risk {R:.2f} >= {c.lean_at:.2f} for {c.lean_hold_s:.0f}s"))
        elif (level > 0 or breaker != "closed") and self._calm_for(now) >= c.calm_hold_s:
            reason = f"risk {R:.2f} < {c.calm_below:.2f} for {self._calm_for(now):.0f}s"
            if level > 2:
                out.append(Decision("set_level", str(level - 1), reason))
            elif breaker == "open":
                out.append(Decision("set_breaker", "half_open", reason))
                if level != 1:
                    out.append(Decision("set_level", "1", reason))
                self.opened_at = None
            elif breaker == "half_open":
                out.append(Decision("set_breaker", "closed", reason))
            elif level > 0:
                out.append(Decision("set_level", str(level - 1), reason))

        if out:
            self.last_change = now
        return out


def reactive_risk(p95_s: float | None, slo_s: float) -> float:
    """The reactive baseline's 'risk': 1 when current p95 is over the SLO, else 0 (no prediction)."""
    return 1.0 if p95_s is not None and p95_s > slo_s else 0.0
