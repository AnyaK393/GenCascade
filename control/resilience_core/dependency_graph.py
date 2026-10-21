"""Dependency graph and cascade risk (guide 6.4).

R(v) = 1 - (1 - p_v) * prod over u in succ(v) of (1 - w_vu * R(u)), computed in reverse
topological order (dependencies first).

Edge weights come from the call type:
- 0.9: synchronous call with no fallback; a stall here stalls the caller
  (gateway -> orchestrator tutor path, orchestrator -> llm_inference).
- 0.6: synchronous with a degraded fallback; the orchestrator answers from hints if RAG is down,
  but RAG time still adds to every tutor request.
- 0.3: call with a default fallback or an isolated pool (quiz path on its own pool; the
  profile lookup has a 0.3 s timeout and a default profile).
"""

import networkx as nx

BLAST_LEVEL = 0.5


def build_graph() -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_edge("gateway", "orchestrator", w=0.9)    # synchronous, critical
    G.add_edge("gateway", "student", w=0.3)         # quiz path, isolated pool
    G.add_edge("orchestrator", "llm_inference", w=0.9)
    G.add_edge("orchestrator", "curriculum_rag", w=0.6)
    G.add_edge("orchestrator", "student", w=0.3)    # profile has a default fallback
    return G


GRAPH = build_graph()


def cascade_risk(own: dict[str, float], G: nx.DiGraph = GRAPH, weight_scale: float = 1.0) -> dict[str, float]:
    """Cascade risk per node from each node's own risk (missing nodes count as 0).
    weight_scale=0 disables the graph (own risk only), for the ablation."""
    R: dict[str, float] = {}
    for v in reversed(list(nx.topological_sort(G))):
        keep = 1.0 - own.get(v, 0.0)
        for u in G.successors(v):
            keep *= 1.0 - weight_scale * G[v][u]["w"] * R[u]
        R[v] = 1.0 - keep
    return R


def blast_radius(own: dict[str, float], G: nx.DiGraph = GRAPH) -> dict:
    """The node with the highest own risk and the services pushed over BLAST_LEVEL because of it."""
    if not own:
        return {"source": None, "services": []}
    source = max(own, key=own.get)
    with_it = cascade_risk(own, G)
    without = cascade_risk({**own, source: 0.0}, G)
    services = [v for v in G.nodes if with_it[v] > BLAST_LEVEL and without[v] <= BLAST_LEVEL]
    return {"source": source if services else None, "services": sorted(services)}


def edges() -> list[tuple[str, str, float]]:
    return [(a, b, d["w"]) for a, b, d in GRAPH.edges(data=True)]
