"""CascadeShield control-room dashboard.

Reads only the resilience core (/state, /history) and Redis (cs:actions), never Prometheus,
so every panel shows the same snapshot. Live panels sit in a fragment that redraws every 2 s.
Operator controls call the core's /ops endpoints or the platform's control API.

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
LEVEL_MEANING = {
    0: "Full Socratic answers from the LLM",
    1: "Shorter LLM answers, less context",
    2: "Cached answers or syllabus passages; no LLM",
    3: "Rule-based hints per topic; no LLM",
    4: "Questions queued; quiz unaffected",
}
SERVICES = ["gateway", "student", "orchestrator", "curriculum_rag", "llm_inference"]
HDR = {"X-CS-Token": settings.cs_token}


@st.cache_resource
def redis_client() -> redis.Redis:
    return redis.Redis(host=settings.redis_host, port=settings.redis_port,
                       password=settings.redis_password, decode_responses=True,
                       socket_timeout=1, socket_connect_timeout=1)


def get(path: str, default):
    try:
        return httpx.get(f"{settings.core_url}{path}", timeout=1.5).json()
    except (httpx.HTTPError, ValueError):
        return default


def call(url: str, body: dict | None = None, label: str = "") -> None:
    try:
        r = httpx.post(url, json=body or {}, headers=HDR, timeout=3)
        r.raise_for_status()
        st.toast(f"{label or url.rsplit('/', 1)[-1]}: ok")
    except httpx.HTTPError as e:
        detail = getattr(getattr(e, "response", None), "text", "") or str(e)
        st.toast(f"{label} failed: {detail[:120]}", icon="⚠️")


def core_ops(**changes) -> None:
    call(f"{settings.core_url}/ops/settings", changes, ", ".join(f"{k}={v}" for k, v in changes.items()))


def risk_colour(r: float | None, threshold: float = 0.8) -> str:
    if r is None:
        return "#9e9e9e"
    return "#2e7d32" if r < 0.5 else "#f9a825" if r < threshold else "#c62828"


def graph_dot(s: dict) -> str:
    cascade, own, thr = s.get("cascade") or {}, s.get("risk") or {}, s.get("threshold", 0.8)
    blast = set((s.get("blast") or {}).get("services", []))
    breaker = (s.get("platform") or {}).get("breaker", "closed")
    lines = ["digraph G {", "rankdir=LR; bgcolor=transparent; nodesep=0.4;",
             'node [shape=box style="rounded,filled" fontcolor=white fontname=Helvetica fontsize=13];',
             'edge [fontname=Helvetica fontsize=10 color="#777777" fontcolor="#777777"];']
    for svc in SERVICES:
        r, o = cascade.get(svc), own.get(svc)
        label = f"{svc}\\ncascade {r:.2f}" + (f" · own {o:.2f}" if o is not None else "") if r is not None else svc
        border = ' color="#ff1744" penwidth=4' if svc in blast else ' color="#00000000"'
        lines.append(f'{svc} [label="{label}" fillcolor="{risk_colour(r, thr)}"{border}];')
    for a, b, w in s.get("edges") or []:
        attrs = f'label="{w}"'
        if (a, b) == ("orchestrator", "llm_inference") and breaker != "closed":
            attrs = f'label="⚡ breaker {breaker}" color="#c62828" fontcolor="#c62828" style=dashed penwidth=2.5'
        lines.append(f"{a} -> {b} [{attrs}];")
    lines.append("}")
    return "\n".join(lines)


# --- sidebar: operator controls -------------------------------------------------------

state0 = get("/state", {})
ops = state0.get("ops") or {}
with st.sidebar:
    st.header("Operator")
    st.caption(f"Platform `{settings.platform_host}` · model `{state0.get('model') or 'none'}`")
    controller = st.selectbox("Controller", ["predictive", "threshold", "reactive"],
                              index=["predictive", "threshold", "reactive"].index(ops.get("controller", "predictive")))
    if controller != ops.get("controller", "predictive"):
        core_ops(controller=controller)
    for key, label, help_ in [
        ("dry_run", "Dry run", "Log decisions without sending them"),
        ("approval", "Approval mode", "Hold each decision for Approve / Reject"),
        ("graph_enabled", "Use dependency graph", "Off: own risk only (ablation)"),
    ]:
        val = st.toggle(label, value=bool(ops.get(key, key == "graph_enabled")), help=help_)
        if ops and val != bool(ops.get(key)):
            core_ops(**{key: val})
    kill = bool(ops.get("kill_switch"))
    if st.button("▶ Resume control" if kill else "⛔ Kill switch", type="primary" if not kill else "secondary",
                 width="stretch", help="Stops all actions and the heartbeat; the platform's failsafe takes over"):
        core_ops(kill_switch=not kill)

    st.divider()
    st.subheader("Exam")
    course = st.selectbox("Course", ["DSA101", "DBMS201", "OS202"])
    if st.button("Schedule exam in 2 minutes", width="stretch"):
        call(f"{settings.core_url}/ops/exam", {"course": course, "in_minutes": 2, "duration_min": 15,
                                               "expected_students": 120, "topics": []}, "schedule exam")

    st.divider()
    st.subheader("Manual")
    level = st.selectbox("Degradation level", list(LEVELS), format_func=LEVELS.get)
    if st.button("Set level", width="stretch"):
        call(f"{settings.control_api}/control/mode", {"level": level, "reason": "manual", "actor": "operator"}, "set level")
    c1, c2 = st.columns(2)
    if c1.button("Open breaker", width="stretch"):
        call(f"{settings.control_api}/control/breaker", {"state": "open", "reason": "manual", "actor": "operator"}, "open")
    if c2.button("Close breaker", width="stretch"):
        call(f"{settings.control_api}/control/breaker", {"state": "closed", "reason": "manual", "actor": "operator"}, "close")

    st.divider()
    st.subheader("Chaos (CHAOS_ENABLED=1)")
    llm = settings.service_url("llm_inference")
    c1, c2 = st.columns(2)
    if c1.button("+1.5 s latency", width="stretch"):
        call(f"{llm}/chaos/latency", {"extra_ms": 1500, "seconds": 120}, "latency")
    if c2.button("Memory leak", width="stretch"):
        call(f"{llm}/chaos/leak", {"mb_per_s": 2, "seconds": 120}, "leak")
    c1, c2 = st.columns(2)
    if c1.button("Clear chaos", width="stretch"):
        call(f"{llm}/chaos/clear", {}, "clear")
    if c2.button("Reset platform", width="stretch"):
        call(f"{settings.control_api}/admin/reset", {}, "reset")


# --- live panels ----------------------------------------------------------------------

@st.fragment(run_every=2)
def live():
    s = get("/state", {"healthy": False, "error": "core unreachable"})
    platform = s.get("platform") or {}
    contained = s.get("contained_service", "llm_inference")
    thr = s.get("threshold", 0.8)
    r = (s.get("risk") or {}).get(contained)
    R = (s.get("cascade") or {}).get(contained)
    lvl, breaker = platform.get("level"), platform.get("breaker", "unknown")
    o = s.get("ops") or {}

    # status banner
    status, colour = ("CRITICAL", "#c62828") if (R or 0) >= thr else \
        ("MITIGATING", "#f9a825") if (lvl or 0) > 0 or breaker != "closed" else ("NOMINAL", "#2e7d32")
    if not s.get("healthy"):
        status, colour = "CONTROL LOOP DOWN", "#616161"
    hb = platform.get("heartbeat_age_s")
    sessions = ((s.get("telemetry") or {}).get("gateway") or {}).get("sessions_active")
    flags = " · ".join(f for f, on in [("DRY RUN", o.get("dry_run")), ("APPROVAL", o.get("approval")),
                                       ("KILL SWITCH", o.get("kill_switch"))] if on)
    exam = platform.get("exam") or {}
    st.markdown(
        f"<div style='background:{colour};color:white;padding:10px 16px;border-radius:8px;font-size:1.25rem'>"
        f"<b>SYSTEM STATUS: {status}</b> &nbsp;·&nbsp; sessions {sessions or 0:.0f} &nbsp;·&nbsp; "
        f"protection {platform.get('protection_mode', '?')} &nbsp;·&nbsp; control {platform.get('control_source', '?')} "
        f"&nbsp;·&nbsp; heartbeat {'missing' if hb is None else f'{hb:.1f}s'} &nbsp;·&nbsp; controller {s.get('controller', '?')}"
        + (f" &nbsp;·&nbsp; exam {exam.get('course')} (floor {exam.get('floor')})" if exam.get("active") else "")
        + (f" &nbsp;·&nbsp; <b>{flags}</b>" if flags else "") + "</div>", unsafe_allow_html=True)
    if not s.get("healthy"):
        st.error(f"{s.get('error')}. The platform's failsafe is in charge.")
    if s.get("model_error"):
        st.warning(s["model_error"])

    col1, col2, col3 = st.columns([1.35, 1, 1.15])
    with col1:
        st.subheader("Topology")
        st.graphviz_chart(graph_dot(s), width="stretch")
        blast = s.get("blast") or {}
        if blast.get("services"):
            st.caption(f"Blast radius from **{blast['source']}**: {', '.join(blast['services'])}")
    with col2:
        st.subheader("Prediction")
        fig = go.Figure(go.Indicator(
            mode="gauge+number", value=R or 0, number={"valueformat": ".2f"},
            title={"text": f"{contained} cascade risk"},
            gauge={"axis": {"range": [0, 1]}, "bar": {"color": risk_colour(R, thr)},
                   "threshold": {"line": {"color": "black", "width": 4}, "value": thr}}))
        fig.update_layout(height=230, margin=dict(l=20, r=20, t=50, b=0))
        st.plotly_chart(fig, width="stretch")
        ttf = s.get("ttf_s")
        if ttf is not None and (r or 0) >= 0.5:
            st.markdown(f"**Estimated stall in ~{ttf:.0f} s** *(estimate)*")
        st.caption(f"own risk {r:.2f} · threshold {thr:.2f}" if r is not None else "warming up")
        factors = s.get("factors") or []
        if factors:
            bar = go.Figure(go.Bar(x=[f["shap"] for f in factors][::-1], y=[f["label"] for f in factors][::-1],
                                   orientation="h", marker_color=["#c62828" if f["shap"] > 0 else "#2e7d32"
                                                                  for f in factors][::-1]))
            bar.update_layout(height=170, margin=dict(l=10, r=10, t=25, b=10), title="Why (SHAP, top 3)",
                              xaxis_title=None)
            st.plotly_chart(bar, width="stretch")
    with col3:
        st.subheader("Containment")
        m1, m2, m3 = st.columns(3)
        m1.metric("Level", LEVELS.get(lvl, "?").split(" ", 1)[0] if lvl is not None else "?")
        m2.metric("Breaker", breaker)
        m3.metric("Admission", platform.get("admission_limit") or "–")
        if lvl is not None:
            st.caption(f"**{LEVELS[lvl]}**: {LEVEL_MEANING[lvl]}")
        pending = s.get("pending")
        if pending:
            with st.container(border=True):
                st.markdown("**Pending action** · " + ", ".join(f"{d['action']} → {d['value']}" for d in pending["decisions"]))
                st.caption(pending["decisions"][0]["reason"])
                a, b = st.columns(2)
                if a.button("✅ Approve", width="stretch", key=f"approve{pending['created']}"):
                    call(f"{settings.core_url}/ops/pending/approve", {}, "approve")
                if b.button("❌ Reject", width="stretch", key=f"reject{pending['created']}"):
                    call(f"{settings.core_url}/ops/pending/reject", {}, "reject")
        try:
            entries = redis_client().xrevrange("cs:actions", count=15)
        except redis.RedisError as e:
            st.warning(f"Redis unreachable: {e}")
            entries = []
        rows = [{"time": datetime.fromtimestamp(float(f.get("ts", 0))).strftime("%H:%M:%S"),
                 "actor": f.get("actor", ""), "action": f"{f.get('action', '')} → {f.get('value', '')}",
                 "reason": f.get("reason", "")} for _, f in entries]
        st.dataframe(rows, hide_index=True, width="stretch", height=300)

    # timeline
    h = get("/history", [])
    if h:
        t = [datetime.fromtimestamp(x["t"]) for x in h]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=t, y=[x["cascade"] for x in h], name="cascade risk", line=dict(color="#c62828", width=2.5)))
        fig.add_trace(go.Scatter(x=t, y=[x["risk"] for x in h], name="own risk", line=dict(color="#ef9a9a", width=1)))
        fig.add_trace(go.Scatter(x=t, y=[x["p95_slo"] for x in h], name="LLM p95 ÷ SLO", line=dict(color="#1565c0", width=2)))
        fig.add_hline(y=thr, line_dash="dash", line_color="#c62828", annotation_text="threshold")
        fig.add_hline(y=1.0, line_dash="dot", line_color="#1565c0", annotation_text="SLO", annotation_position="bottom right")
        for x in h:
            if x["decisions"]:
                fig.add_vline(x=datetime.fromtimestamp(x["t"]), line_color="#6a1b9a", line_width=1)
                fig.add_annotation(x=datetime.fromtimestamp(x["t"]), y=1.15, text=" ".join(x["decisions"]),
                                   showarrow=False, font=dict(size=9, color="#6a1b9a"), textangle=-30)
        fig.update_layout(height=280, margin=dict(l=10, r=10, t=30, b=10), yaxis=dict(range=[0, 1.3]),
                          legend=dict(orientation="h", y=1.18), title="Last 10 minutes")
        st.plotly_chart(fig, width="stretch")

    upcoming = s.get("calendar") or []
    if upcoming:
        st.caption("Exams: " + " · ".join(f"{e['course']} {e['start'][11:16]} ({e['status']})" for e in upcoming))
    st.caption(f"Snapshot {time.strftime('%H:%M:%S', time.localtime(s['ts'])) if s.get('ts') else '–'}")


live()
