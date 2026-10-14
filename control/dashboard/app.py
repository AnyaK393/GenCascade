"""CascadeShield control-room dashboard (Phase 1 skeleton).

Reads only the resilience core's /state and Redis, never Prometheus, so every panel shows
the same snapshot. Live panels sit in fragments that redraw every 2 s.

Run: uv run streamlit run dashboard/app.py
"""

import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import plotly.graph_objects as go
import redis
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from resilience_core.settings import settings  # noqa: E402

st.set_page_config(page_title="CascadeShield", page_icon="🛡️", layout="wide")

LEVELS = {0: "L0 Full", 1: "L1 Lean", 2: "L2 Cache + RAG", 3: "L3 Static hints", 4: "L4 Shed"}
EDGES = [("gateway", "orchestrator"), ("gateway", "student"), ("orchestrator", "llm_inference"),
         ("orchestrator", "curriculum_rag"), ("orchestrator", "student")]


@st.cache_resource
def redis_client() -> redis.Redis:
    return redis.Redis(host=settings.redis_host, port=settings.redis_port,
                       password=settings.redis_password, decode_responses=True,
                       socket_timeout=1, socket_connect_timeout=1)


def core_state() -> dict:
    try:
        return httpx.get(f"{settings.core_url}/state", timeout=1.5).json()
    except (httpx.HTTPError, ValueError) as e:
        return {"healthy": False, "error": f"core unreachable: {e}"}


def risk_colour(r: float | None) -> str:
    if r is None:
        return "#9e9e9e"
    return "#2e7d32" if r < 0.5 else "#f9a825" if r < 0.8 else "#c62828"


def graph_dot(risk: dict, breaker: str) -> str:
    lines = ["digraph G {", "rankdir=LR; bgcolor=transparent;",
             'node [shape=box style="rounded,filled" fontcolor=white fontname=Helvetica fontsize=14];']
    for svc in ["gateway", "student", "orchestrator", "curriculum_rag", "llm_inference"]:
        r = risk.get(svc)
        label = f"{svc}\\n{r:.2f}" if r is not None else svc
        lines.append(f'{svc} [label="{label}" fillcolor="{risk_colour(r)}"];')
    for a, b in EDGES:
        attrs = ""
        if (a, b) == ("orchestrator", "llm_inference") and breaker != "closed":
            attrs = f' [label="breaker {breaker}" color="#c62828" style=dashed penwidth=2]'
        lines.append(f"{a} -> {b}{attrs};")
    lines.append("}")
    return "\n".join(lines)


def control_call(path: str, body: dict) -> None:
    try:
        r = httpx.post(f"{settings.control_api}{path}", json=body,
                       headers={"X-CS-Token": settings.cs_token}, timeout=2)
        r.raise_for_status()
        st.toast(f"{path}: ok")
    except httpx.HTTPError as e:
        st.toast(f"{path} failed: {e}", icon="⚠️")


# --- sidebar: operator controls -------------------------------------------------------

with st.sidebar:
    st.header("Operator")
    st.caption(f"Platform: `{settings.platform_host}`")
    level = st.radio("Degradation level", list(LEVELS), format_func=LEVELS.get, horizontal=False)
    if st.button("Set level", width="stretch"):
        control_call("/control/mode", {"level": level, "reason": "manual", "actor": "operator"})
    c1, c2 = st.columns(2)
    if c1.button("Open breaker", width="stretch"):
        control_call("/control/breaker", {"state": "open", "reason": "manual", "actor": "operator"})
    if c2.button("Close breaker", width="stretch"):
        control_call("/control/breaker", {"state": "closed", "reason": "manual", "actor": "operator"})
    if st.button("Reset platform", width="stretch"):
        control_call("/admin/reset", {})


# --- live panels ----------------------------------------------------------------------

st.title("🛡️ CascadeShield control room")


@st.fragment(run_every=2)
def live():
    s = core_state()
    platform = s.get("platform") or {}
    risk = s.get("risk") or {}
    contained = s.get("contained_service", "llm_inference")
    r = risk.get(contained)
    lvl, breaker = platform.get("level"), platform.get("breaker", "unknown")

    if not s.get("healthy"):
        st.error(f"Control loop not healthy: {s.get('error')}. The platform's failsafe is in charge.")
    status = "CRITICAL" if (r or 0) >= 0.8 else "MITIGATING" if (lvl or 0) > 0 else "NOMINAL"
    hb = platform.get("heartbeat_age_s")
    st.markdown(
        f"**SYSTEM STATUS: {status}** · protection `{platform.get('protection_mode', '?')}` · "
        f"control `{platform.get('control_source', '?')}` · heartbeat "
        f"{'missing' if hb is None else f'{hb:.1f}s ago'}"
    )

    col1, col2, col3 = st.columns([1.3, 1, 1.2])
    with col1:
        st.subheader("Topology")
        st.graphviz_chart(graph_dot(risk, breaker), width="stretch")
    with col2:
        st.subheader("Risk")
        fig = go.Figure(go.Indicator(
            mode="gauge+number", value=r or 0, number={"valueformat": ".2f"},
            title={"text": contained},
            gauge={"axis": {"range": [0, 1]}, "bar": {"color": risk_colour(r)},
                   "threshold": {"line": {"color": "black", "width": 4},
                                 "value": s.get("threshold", 0.8)}},
        ))
        fig.update_layout(height=260, margin=dict(l=20, r=20, t=50, b=10))
        st.plotly_chart(fig, width="stretch")
        m1, m2 = st.columns(2)
        m1.metric("Level", LEVELS.get(lvl, "?") if lvl is not None else "?")
        m2.metric("Breaker", breaker)
        tel = (s.get("telemetry") or {}).get(contained) or {}
        if tel:
            m3, m4 = st.columns(2)
            p95 = tel.get("p95_s")
            m3.metric("LLM p95", f"{p95:.1f}s" if p95 is not None else "–")
            m4.metric("Queue", f"{tel.get('queue_depth') or 0:.0f}")
    with col3:
        st.subheader("Containment log")
        try:
            entries = redis_client().xrevrange("cs:actions", count=20)
        except redis.RedisError as e:
            st.warning(f"Redis unreachable: {e}")
            entries = []
        rows = [{
            "time": datetime.fromtimestamp(float(f.get("ts", 0))).strftime("%H:%M:%S"),
            "actor": f.get("actor", ""),
            "action": f"{f.get('action', '')} → {f.get('value', '')}",
            "reason": f.get("reason", ""),
        } for _, f in entries]
        st.dataframe(rows, hide_index=True, width="stretch", height=420)

    st.caption(f"Snapshot {time.strftime('%H:%M:%S', time.localtime(s['ts'])) if s.get('ts') else '–'}")


live()
