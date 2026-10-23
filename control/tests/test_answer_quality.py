import csv
import json

from experiments import answer_quality as aq


def write(path, rows, header):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def test_score_means_and_agreement(tmp_path, monkeypatch):
    monkeypatch.setattr(aq, "RATINGS_DIR", tmp_path)
    monkeypatch.setattr(aq, "OUT", tmp_path / "aq.json")
    write(tmp_path / "key.csv", [[1, 0, "llm"], [2, 0, "llm"], [3, 3, "hint"]], ["id", "level", "source"])
    write(tmp_path / "a.csv", [[1, "", "", "", 5], [2, "", "", "", 4], [3, "", "", "", 2]],
          ["id", "course", "question", "answer", "rating"])
    write(tmp_path / "b.csv", [[1, "", "", "", 4], [2, "", "", "", 4], [3, "", "", "", 4]],
          ["id", "course", "question", "answer", "rating"])
    aq.score([tmp_path / "a.csv", tmp_path / "b.csv"])
    out = json.loads((tmp_path / "aq.json").read_text())
    assert out["mean_by_level"] == {"0": 4.25, "3": 3.0}
    assert out["agreement_within_1"] == round(2 / 3, 3)


def test_rejects_out_of_range_rating(tmp_path):
    import pytest
    write(tmp_path / "r.csv", [[1, "", "", "", 0]], ["id", "course", "question", "answer", "rating"])
    with pytest.raises(SystemExit, match="1-5"):
        aq.read_ratings(tmp_path / "r.csv")


def test_excluded_item_dropped_for_every_rater(tmp_path, monkeypatch):
    monkeypatch.setattr(aq, "RATINGS_DIR", tmp_path)
    monkeypatch.setattr(aq, "OUT", tmp_path / "aq.json")
    write(tmp_path / "key.csv", [[1, 0, "llm"], [2, 0, "llm"]], ["id", "level", "source"])
    write(tmp_path / "a.csv", [[1, "", "", "", 4], [2, "", "", "", 0]], ["id", "course", "question", "answer", "rating"])
    write(tmp_path / "b.csv", [[1, "", "", "", 4], [2, "", "", "", 5]], ["id", "course", "question", "answer", "rating"])
    aq.score([tmp_path / "a.csv", tmp_path / "b.csv"], {2: "malformed question"})
    out = json.loads((tmp_path / "aq.json").read_text())
    assert out["answers_rated"] == 1 and out["excluded"] == {"2": "malformed question"}
