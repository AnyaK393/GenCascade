from resilience_core.containment_engine import ContainmentEngine, EngineConfig, Observation, reactive_risk
from resilience_core.dependency_graph import blast_radius, cascade_risk
from resilience_core.risk import threshold_risk


class Sim:
    """Feeds the engine one risk sample every 2 s and applies its decisions."""

    def __init__(self, threshold=0.8, ladder="full"):
        self.e = ContainmentEngine(EngineConfig(threshold=threshold, ladder=ladder))
        self.t, self.level, self.breaker, self.log = 0.0, 0, "closed", []

    def run(self, risk, seconds, demand=None, **kw):
        for _ in range(int(seconds / 2)):
            self.t += 2
            for d in self.e.decide(Observation(self.t, risk, self.level, self.breaker, demand=demand, **kw)):
                self.log.append((self.t, d.action, d.value))
                if d.action == "set_level":
                    self.level = int(d.value)
                else:
                    self.breaker = d.value
        return self


def test_breach_opens_breaker_after_4s():
    s = Sim().run(0.1, 10).run(0.9, 2)
    assert s.breaker == "closed"
    s.run(0.9, 4)
    assert (s.breaker, s.level) == ("open", 2)


def test_lean_needs_6s_and_rate_limit_holds():
    s = Sim().run(0.65, 4)
    assert s.level == 0
    s.run(0.65, 4)
    assert s.level == 1
    assert len(s.log) == 1


def test_escalates_to_hints_only_if_risk_keeps_rising():
    s = Sim().run(0.9, 6)
    assert s.level == 2
    s.run(0.9, 40)  # flat, not rising
    assert s.level == 2
    s2 = Sim().run(0.85, 6)
    for r in (0.86, 0.88, 0.9, 0.92, 0.94, 0.96, 0.97, 0.98, 0.99):
        s2.run(r, 4)
    assert s2.level == 3


def test_shed_when_admission_at_minimum_and_queue_growing():
    s = Sim()
    s.level, s.breaker = 3, "open"
    s.run(0.7, 12, admission_limit=1, queue_growth_per_s=0.4)
    assert s.level == 4


def test_step_down_sequence_one_notch_per_calm_period():
    s = Sim()
    s.level, s.breaker = 3, "open"
    states = []
    for _ in range(6):
        s.run(0.1, 32)
        states.append((s.level, s.breaker))
    assert states == [(2, "open"), (1, "half_open"), (1, "closed"), (0, "closed"), (0, "closed"), (0, "closed")]
    gaps = [b[0] - a[0] for a, b in zip(s.log, s.log[1:]) if b[0] != a[0]]
    assert all(g >= 30 for g in gaps)


def test_mid_risk_blocks_step_down():
    s = Sim()
    s.level, s.breaker = 2, "open"
    s.run(0.1, 20).run(0.55, 2).run(0.1, 20)
    assert (s.level, s.breaker) == (2, "open")


def test_no_prediction_no_action():
    s = Sim()
    assert s.e.decide(Observation(0, None, 0, "closed")) == []


def test_reactive_risk():
    assert reactive_risk(17, 16) == 1.0 and reactive_risk(None, 16) == 0.0 and reactive_risk(15, 16) == 0.0


def test_cascade_risk_and_blast_radius():
    R = cascade_risk({"llm_inference": 0.9})
    assert R["llm_inference"] == 0.9
    assert abs(R["orchestrator"] - 0.81) < 1e-9  # 1 - (1 - 0.9 * 0.9)
    assert abs(R["gateway"] - 0.9 * 0.81) < 1e-9
    assert R["student"] == 0.0
    br = blast_radius({"llm_inference": 0.9, "student": 0.1})
    assert br == {"source": "llm_inference", "services": ["gateway", "llm_inference", "orchestrator"]}
    assert cascade_risk({"llm_inference": 0.9}, weight_scale=0)["gateway"] == 0.0


def test_threshold_risk():
    assert threshold_risk(None, 10) == 0.0
    assert threshold_risk(5, 10) == 0.0
    assert threshold_risk(7.5, 10) == 0.5
    assert threshold_risk(10, 10) == 1.0
    assert threshold_risk(30, 10) == 1.0


def test_binary_ladder_uses_only_l0_and_l3():
    s = Sim(ladder="binary").run(0.65, 20)
    assert s.level == 0  # no lean step
    s.run(0.9, 6)
    assert (s.level, s.breaker) == (3, "open")
    s.run(0.1, 32)
    assert (s.level, s.breaker) == (0, "half_open")
    s.run(0.1, 32)
    assert (s.level, s.breaker) == (0, "closed")
    assert {int(v) for _, a, v in s.log if a == "set_level"} <= {0, 3}


def test_timed_probe_when_risk_is_stuck_below_threshold():
    """The first comparison's failure mode: breaker open, risk frozen at 0.66 (threshold 0.67)."""
    s = Sim(threshold=0.67).run(0.9, 6)
    assert (s.level, s.breaker) == (2, "open")
    s.run(0.66, 54)
    assert s.breaker == "open"  # before 60 s: no probe
    s.run(0.66, 8)
    assert (s.level, s.breaker) == (1, "half_open")


def test_failed_probe_reopens_and_backs_off():
    s = Sim(threshold=0.67).run(0.9, 6).run(0.66, 64)
    assert s.breaker == "half_open"
    s.run(0.9, 6)  # probe overloads the LLM
    assert (s.level, s.breaker) == (2, "open") and s.e.probe_wait == 120
    s.run(0.66, 100)
    assert s.breaker == "open"  # backed off: no probe before 120 s
    s.run(0.66, 24)
    assert s.breaker == "half_open"


def test_half_open_waits_for_demand_to_fall_before_closing():
    """The second comparison's failure mode: 10 % probes look calm while 40 students are still online."""
    s = Sim(threshold=0.67).run(0.9, 6, demand=20)  # breaks at 20 sessions
    s.run(0.3, 64, demand=40)
    assert s.breaker == "half_open"  # probe started
    s.run(0.3, 120, demand=40)
    assert s.breaker == "half_open"  # calm, but demand is still above the breaking load
    s.run(0.3, 40, demand=15)
    assert s.breaker == "closed"  # 15 <= 80 % of 20


def test_reopening_soon_after_closing_backs_off():
    s = Sim(threshold=0.67).run(0.9, 6).run(0.3, 64).run(0.3, 32)
    assert s.breaker == "closed"
    s.run(0.9, 6)  # re-broken 6 s after closing
    assert s.breaker == "open" and s.e.probe_wait == 120
