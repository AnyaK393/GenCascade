import numpy as np
import pandas as pd

from experiments.evaluate import choose_threshold, event_metrics, false_alarms


def episode(onset_at=None, n=200, ep="e1"):
    t = np.arange(n) * 2.0
    tto = (onset_at - t) if onset_at is not None else np.full(n, np.nan)
    y = ((tto > 0) & (tto <= 90)).astype(int)
    df = pd.DataFrame({"episode_id": ep, "service": "llm_inference", "t": t, "y": y, "time_to_onset_s": tto})
    return df if onset_at is None else df[t < onset_at]  # rows inside the failure are excluded


def test_recall_and_lead_time():
    df = episode(onset_at=300)
    score = np.where((df["t"] >= 260) & (df["t"] < 300), 0.9, 0.1)  # alarm 40 s ahead
    m = event_metrics(df, score, 0.5)
    assert m["onsets"] == 1 and m["recall"] == 1.0 and m["lead_median_s"] == 40
    assert m["false_alarms"] == 0


def test_missed_onset_and_false_alarm_runs():
    df = episode(onset_at=None, n=1800)  # one safe hour
    score = np.zeros(len(df))
    score[100:110] = 0.9  # one run of 10 rows = 1 false alarm
    score[500] = 0.9  # another
    fa, hours = false_alarms(df, score >= 0.5)
    assert (fa, hours) == (2, 1.0)
    assert choose_threshold(df, score, max_fa_per_hour=1.0) == 0.91  # 2 alarms/h at <= 0.9
    assert choose_threshold(df, score, max_fa_per_hour=2.0) == 0.05
    m = event_metrics(pd.concat([df, episode(onset_at=300, ep="e2")]), np.concatenate([score, np.zeros(150)]), 0.5)
    assert m["recall"] == 0.0 and m["onsets"] == 1
