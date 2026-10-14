from resilience_core.containment import ControlState, ThresholdPolicy
from resilience_core.risk import threshold_risk


def apply(state: ControlState, decisions) -> ControlState:
    for d in decisions:
        if d.action == "set_level":
            state.level = int(d.value)
        else:
            state.breaker = d.value
    return state


def test_threshold_risk():
    assert threshold_risk(None, 10) == 0.0
    assert threshold_risk(5, 10) == 0.0
    assert threshold_risk(7.5, 10) == 0.5
    assert threshold_risk(10, 10) == 1.0
    assert threshold_risk(30, 10) == 1.0


def test_opens_at_threshold_and_is_idempotent():
    p, s = ThresholdPolicy(), ControlState()
    assert p.decide(0.79, 0, s) == []
    apply(s, p.decide(0.85, 2, s))
    assert (s.breaker, s.level) == ("open", 3)
    assert p.decide(0.95, 4, s) == []


def test_recovers_through_half_open():
    p, s = ThresholdPolicy(hold_s=30), ControlState(level=3, breaker="open")
    assert p.decide(0.1, 0, s) == []
    assert p.decide(0.1, 29, s) == []
    apply(s, p.decide(0.1, 30, s))
    assert (s.breaker, s.level) == ("half_open", 1)
    # the probe step needs its own hold period
    assert p.decide(0.1, 40, s) == []
    apply(s, p.decide(0.1, 60, s))
    assert (s.breaker, s.level) == ("closed", 0)


def test_mid_band_resets_the_hold_timer():
    p, s = ThresholdPolicy(hold_s=30), ControlState(level=3, breaker="open")
    p.decide(0.1, 0, s)
    p.decide(0.6, 20, s)  # between close_below and open_at
    assert p.decide(0.1, 35, s) == []
    assert p.decide(0.1, 65, s) != []


def test_probe_failure_reopens():
    p, s = ThresholdPolicy(), ControlState(level=1, breaker="half_open")
    apply(s, p.decide(0.9, 0, s))
    assert (s.breaker, s.level) == ("open", 3)
