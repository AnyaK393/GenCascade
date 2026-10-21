import json

import numpy as np
import pandas as pd

from experiments.run_matrix import analyze_run, fmt_ci, mean_ci

SERVICES = ["gateway", "student", "orchestrator", "curriculum_rag", "llm_inference"]


def make_run(tmp_path, llm_p95, alarm_at=None):
    t0, n = 1000.0, len(llm_p95)
    t = t0 + np.arange(n) * 2.0
    rows = []
    for s in SERVICES:
        for i, ti in enumerate(t):
            p95 = llm_p95[i] if s in ("llm_inference", "orchestrator", "gateway") else 0.01
            rows.append({"t": ti, "service": s, "p95_s": p95, "error_rate": 0.0, "queue_depth": 0.0})
    pd.DataFrame(rows).to_parquet(tmp_path / "series.parquet")
    core = [{"t": ti, "signal": "cs_core_cascade_risk", "value": 0.9 if alarm_at is not None and ti >= t0 + alarm_at else 0.1}
            for ti in t]
    pd.DataFrame(core).to_parquet(tmp_path / "core.parquet")
    reqs = [
        {"t": t0, "kind": "tutor", "student": "a", "status": 200, "latency_s": 2, "level": 0},
        {"t": t0, "kind": "tutor", "student": "a", "status": 200, "latency_s": 20, "level": 0},  # slow -> a fails
        {"t": t0, "kind": "tutor", "student": "b", "status": 200, "latency_s": 1, "level": 2},
        {"t": t0, "kind": "tutor", "student": "c", "status": 504, "latency_s": 30, "level": None},  # c fails
        {"t": t0, "kind": "quiz", "student": "q", "status": 202, "latency_s": 0.1, "key": "k1", "duplicate": False},
        {"t": t0, "kind": "quiz", "student": "q", "status": 202, "latency_s": 0.1, "key": "k1", "duplicate": True},
        {"t": t0, "kind": "quiz", "student": "r", "status": 202, "latency_s": 0.1, "key": "k2", "duplicate": False},
    ]
    (tmp_path / "requests.jsonl").write_text("\n".join(json.dumps(r) for r in reqs) + "\n")
    meta = {"variant": "cascadeshield", "run": 1, "export_start": t0, "export_end": float(t[-1]), "threshold": 0.8,
            "student_stats": {"committed": 1},
            "scenario": {"peak_users": 40, "fault": {"start_s": 180, "body": {"seconds": 40}}}}
    (tmp_path / "meta.json").write_text(json.dumps(meta))
    return tmp_path


def test_analyze_run_metrics(tmp_path):
    p95 = [5.0] * 100 + [20.0] * 30 + [5.0] * 70  # failure from t+200 s to t+260 s
    m = analyze_run(make_run(tmp_path, p95, alarm_at=160), utility=None)
    assert abs(m["session_failure_rate"] - 2 / 5) < 1e-9  # a and c fail out of a, b, c, q, r
    assert (m["quiz_accepted"], m["quiz_committed"], m["quiz_lost"], m["quiz_duplicates"]) == (2, 1, 1, 1)
    assert m["slo_violation_s"] == 60  # 30 rows x 2 s over the gateway SLO (18 s)
    assert m["cascade_depth"] == 3 and set(m["failed_services"]) == {"llm_inference", "orchestrator", "gateway"}
    assert m["lead_time_s"] == 40  # onset at +200 s, alarm at +160 s
    assert m["recovery_s"] == 40  # fault ends at +220 s; all under SLO from +260 s
    assert m["level_shares"] == {0: round(2 / 3, 3), 2: round(1 / 3, 3)}


def test_learning_utility_with_ratings(tmp_path):
    m = analyze_run(make_run(tmp_path, [5.0] * 60), utility={0: 4.0, 2: 3.0})
    assert abs(m["learning_utility_retained"] - (4 + 4 + 3 + 0) / 4 / 4.0) < 1e-9
    assert m["lead_time_s"] is None and m["cascade_depth"] == 0


def test_mean_ci():
    m, h, n = mean_ci([1.0, 2.0, 3.0])
    assert m == 2.0 and n == 3 and abs(h - 4.303 * 1.0 / 3 ** 0.5) < 1e-9
    assert fmt_ci((0.25, 0.05, 3), "pct") == "25.0 % ± 5.0"
    assert mean_ci([None, None]) is None
