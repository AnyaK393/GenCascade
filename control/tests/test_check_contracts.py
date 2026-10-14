import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_contracts", ROOT / "scripts" / "check_contracts.py")
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)


def test_contract_parses_every_service():
    expected = cc.parse_contract(ROOT / "contracts" / "metrics.md", phase=1)
    assert "cs_llm_queue_depth" in expected["llm_inference"]
    assert "cs_llm_queue_depth" not in expected["gateway"]
    assert "process_cpu_seconds_total" in expected["student"]
    assert "cs_admission_limit" not in expected["gateway"]
    assert "cs_admission_limit" in cc.parse_contract(ROOT / "contracts" / "metrics.md", 3)["gateway"]


def test_presence_and_service_label():
    text = "\n".join([
        "# TYPE cs_http_requests_total counter",
        'cs_http_requests_total{route="/x",service="gateway",status="200"} 3.0',
        "# TYPE cs_shed_requests_total counter",  # declared, no samples yet
        'cs_inflight_requests 1.0',  # missing service label
        'cs_http_request_duration_seconds_count{route="/p/{id}",service="student"} 2.0',
    ])
    samples = cc.parse_exposition(text)
    assert cc.present("cs_http_requests_total", samples) == ['{route="/x",service="gateway",status="200"}']
    assert cc.present("cs_shed_requests_total", samples) == []
    assert cc.present("cs_inflight_requests", samples) == [""]
    assert cc.present("cs_sessions_active", samples) is None
    assert cc.present("cs_http_request_duration_seconds", samples) == ['{route="/p/{id}",service="student"}']
