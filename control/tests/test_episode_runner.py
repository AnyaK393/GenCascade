import pandas as pd
import yaml

from chaos import locustfile
from chaos.episode_runner import CONFIG, plan_episode, shape_length, validate

CFG = yaml.safe_load(CONFIG.read_text())


def test_plans_are_deterministic_and_follow_the_mix():
    assert plan_episode(CFG, 7) == plan_episode(CFG, 7)
    plans = [plan_episode(CFG, 2026000 + i) for i in range(300)]
    share = pd.Series([p["category"] for p in plans]).value_counts(normalize=True)
    assert abs(share["fail"] - 0.60) < 0.08 and abs(share["safe"] - 0.25) < 0.08
    for p in plans:
        sc = p["scenario"]
        assert p["load_s"] == sc["lead_s"] + shape_length(sc["shape"], sc)
        if p["category"] == "safe":
            assert p["fault"] is None and p["peak_users"] < CFG["capacity_users"]
        if p["category"] == "fault_only":
            assert p["fault"] is not None
        if p["fault"]:
            assert sc["lead_s"] + CFG["fault_start_s"][0] <= p["fault"]["start_s"] <= p["load_s"]


def test_planned_shapes_run_to_completion_in_locust():
    for i in range(40):
        sc = plan_episode(CFG, 99000 + i)["scenario"]
        shape = locustfile.SHAPES[sc["shape"]]
        length = shape_length(sc["shape"], sc)
        assert shape(length - 1, sc) is not None
        assert shape(length + 5, sc) is None


def test_validate_flags_restarts_and_gaps():
    t = [float(x) for x in range(0, 200, 2)]
    rows = [{"t": ti, "service": s, "process_start": 1.0, "sample_ts": ti}
            for s in ["gateway", "student", "orchestrator", "curriculum_rag", "llm_inference"] for ti in t]
    df = pd.DataFrame(rows)
    assert validate(df, 0, 198) == []
    df.loc[(df.service == "student") & (df.t > 100), "process_start"] = 2.0
    df.loc[(df.service == "gateway") & (df.t > 150), "sample_ts"] = 150.0
    problems = validate(df, 0, 198)
    assert "student restarted" in problems and any(p.startswith("gateway scrape gap") for p in problems)


def test_question_bank_has_no_self_comparisons():
    from chaos.questions import COURSES, bank
    for c in COURSES:
        qs = [q for _, q in bank(c)]
        assert len(qs) == 300
        assert not any("arrays different from arrays" in q for q in qs)
        assert c == "DSA101" or not any("different from arrays" in q for q in qs)
