from datetime import datetime, timedelta, timezone

from resilience_core.calendar import CALENDAR_FILE, Exam, ExamCalendar

T0 = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)


def exam():
    return Exam(course="DSA101", start=T0, duration_min=60, expected_students=100, topics=["bst"])


def steps(cal, now):
    out = [d.step for d in cal.due(now)]
    for d in cal.due(now):
        cal.mark(d)
    return out


def test_prewarm_start_end_in_order_and_once():
    cal = ExamCalendar([exam()], T0 - timedelta(hours=1))
    assert steps(cal, T0 - timedelta(minutes=11)) == []
    assert steps(cal, T0 - timedelta(minutes=10)) == ["prewarm"]
    assert steps(cal, T0 - timedelta(minutes=5)) == []
    assert steps(cal, T0) == ["start"]
    assert steps(cal, T0 + timedelta(minutes=30)) == []
    assert steps(cal, T0 + timedelta(minutes=60)) == ["end"]
    assert steps(cal, T0 + timedelta(minutes=61)) == []


def test_restart_mid_exam_restarts_without_prewarm():
    cal = ExamCalendar([exam()], T0 + timedelta(minutes=20))
    assert steps(cal, T0 + timedelta(minutes=20)) == ["start"]


def test_finished_exam_is_ignored():
    cal = ExamCalendar([exam()], T0 + timedelta(hours=2))
    assert steps(cal, T0 + timedelta(hours=2)) == []


def test_calendar_file_loads():
    cal = ExamCalendar.load(CALENDAR_FILE, T0 - timedelta(days=30))
    assert len(cal.exams) >= 1 and all(e.start.tzinfo for e in cal.exams.values())
