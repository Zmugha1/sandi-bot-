"""
Interactive Knowledge Graph visualization.
Builds streamlit-agraph nodes/edges from NetworkX graph. Client-centric subgraph with filters and depth.
Deterministic; no LLM. Evidence (page, snippet, doc_id) attached to edges and node details.
"""
from typing import Dict, Any, List, Tuple, Optional, Set
import networkx as nx

from . import ontology as o
from . import build_graph as bg
from . import recommendations as rec


# Focus filter values
FOCUS_ALL = "All"
FOCUS_TRAITS = "Traits"
FOCUS_DRIVERS = "Drivers"
FOCUS_RISKS = "Risks"
FOCUS_RECOMMENDATIONS = "Recommendations"
FOCUS_DOCUMENTS = "Documents"

DEFAULT_NODE_LIMIT = 25
MAX_DEPTH = 2


def _node_type(nid: str, G: nx.MultiDiGraph) -> str:
    """Return node type: client, trait, driver, risk, action, document."""
    if not G.has_node(nid):
        return "unknown"
    nt = G.nodes[nid].get("node_type") or ""
    s = str(nid).lower()
    if "client:" in s or nt == o.NODE_CLIENT:
        return "client"
    if "trait:" in s or nt == o.NODE_TRAIT:
        return "trait"
    if "driver:" in s or nt == o.NODE_DRIVER:
        return "driver"
    if "risk:" in s or nt == o.NODE_RISK:
        return "risk"
    if "coachingaction:" in s or "action:" in s or nt == o.NODE_COACHING_ACTION:
        return "action"
    if "document:" in s or nt == o.NODE_DOCUMENT:
        return "document"
    return "unknown"


def _get_label(G: nx.MultiDiGraph, nid: str) -> str:
    label = G.nodes[nid].get("label") or G.nodes[nid].get("label")
    if label is not None:
        return str(label)[:80]
    return str(nid).split(":", 1)[-1] if ":" in str(nid) else str(nid)[:80]


def _collect_neighbors_at_depth(G: nx.MultiDiGraph, client_id: str, depth: int) -> Set[str]:
    """BFS from client_id up to depth. Returns set of node ids."""
    if depth < 1 or not G.has_node(client_id):
        return {client_id}
    seen = {client_id}
    frontier = [client_id]
    for _ in range(depth):
        next_frontier = []
        for n in frontier:
            for succ in G.successors(n):
                if succ not in seen:
                    seen.add(succ)
                    next_frontier.append(succ)
            for pred in G.predecessors(n):
                if pred not in seen:
                    seen.add(pred)
                    next_frontier.append(pred)
        frontier = next_frontier
    return seen


def _filter_by_focus(
    nodes: Set[str],
    G: nx.MultiDiGraph,
    focus: str,
    show_documents: bool,
) -> Set[str]:
    if focus == FOCUS_ALL:
        if not show_documents:
            nodes = {n for n in nodes if _node_type(n, G) != "document"}
        return nodes
    type_map = {
        FOCUS_TRAITS: "trait",
        FOCUS_DRIVERS: "driver",
        FOCUS_RISKS: "risk",
        FOCUS_RECOMMENDATIONS: "action",
        FOCUS_DOCUMENTS: "document",
    }
    want = type_map.get(focus, "")
    if not want:
        return nodes
    return {n for n in nodes if _node_type(n, G) == want}


def _limit_nodes(nodes: Set[str], G: nx.MultiDiGraph, client_id: str, limit: int) -> Set[str]:
    """Keep client + limit-1 others. Prefer neighbors by type diversity."""
    if len(nodes) <= limit:
        return nodes
    client_type = _node_type(client_id, G)
    others = [n for n in nodes if n != client_id]
    # Prefer traits, then drivers, then risks, then rest
    def order(n):
        t = _node_type(n, G)
        if t == "trait":
            return 0
        if t == "driver":
            return 1
        if t == "risk":
            return 2
        if t == "action":
            return 3
        return 4
    others.sort(key=order)
    return {client_id} | set(others[: limit - 1])


def get_clients_in_graph(G: nx.MultiDiGraph) -> List[str]:
    """Return list of client names (labels) that exist in the graph."""
    out = []
    for nid in G.nodes():
        if _node_type(nid, G) == "client":
            label = _get_label(G, nid)
            if label and label not in out:
                out.append(label)
    return sorted(out)


def get_node_details(
    G: nx.MultiDiGraph,
    nid: str,
) -> Dict[str, Any]:
    """
    Return details for the right panel: type, label, connected edges (relation + evidence), why (for actions).
    """
    if not G.has_node(nid):
        return {"type": "unknown", "label": str(nid), "edges": [], "evidence": [], "why": None}
    ntype = _node_type(nid, G)
    label = _get_label(G, nid)
    edges_out = []
    evidence_list = []
    for u, v, key in list(G.edges(keys=True)):
        if u != nid and v != nid:
            continue
        try:
            data = G.edges[u, v, key]
        except (KeyError, TypeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        rel = data.get("relation") or (str(key) if isinstance(key, str) else str(key) if key is not None else "link")
        other = v if u == nid else u
        other_label = _get_label(G, other) if G.has_node(other) else str(other)
        edges_out.append({"relation": rel, "target": other_label})
        doc_id = data.get("doc_id")
        page = data.get("page")
        snippet = data.get("snippet")
        if doc_id or page is not None or snippet:
            evidence_list.append({
                "doc_id": str(doc_id) if doc_id is not None else "",
                "page": page,
                "snippet": (str(snippet)[:200] + "..." if len(str(snippet or "")) > 200 else (snippet or "")),
            })
    return {
        "type": ntype,
        "label": label,
        "edges": edges_out,
        "evidence": evidence_list,
        "why": None,  # Filled for action nodes from recommendations
    }


def build_agraph_elements(
    G: nx.MultiDiGraph,
    client_name: str,
    focus: str = FOCUS_ALL,
    depth: int = 1,
    limit: int = DEFAULT_NODE_LIMIT,
    show_documents: bool = False,
) -> Tuple[List[Dict], List[Dict], Dict[str, Dict[str, Any]]]:
    """
    Build nodes and edges for streamlit-agraph, plus a node_id -> details map for the right panel.

    Returns:
      (nodes_for_agraph, edges_for_agraph, node_details_map)
    nodes_for_agraph: list of {"id", "label", "type" for color/size}
    edges_for_agraph: list of {"source", "target", "label" (relation)}
    node_details_map: node_id -> get_node_details output (with evidence, why for actions)
    """
    cid = o.client_id(client_name)
    if not G.has_node(cid):
        # Add recommendation nodes as virtual if we have traits/drivers/risks from graph
        tdr = bg.get_client_traits_drivers_risks(G, client_name)
        traits = [{"label": t.get("label"), "evidence": t.get("evidence")} for t in tdr.get("traits") or []]
        drivers = [{"label": d.get("label"), "evidence": d.get("evidence")} for d in tdr.get("drivers") or []]
        risks = [{"label": r.get("label"), "evidence": r.get("evidence")} for r in tdr.get("risks") or []]
        recs = rec.get_recommendations(traits, drivers, risks, max_n=5)
        nodes = [{"id": "no_client", "label": "No graph data", "type": "client"}]
        edges = []
        details = {"no_client": {"type": "client", "label": "Build insights for this client first.", "edges": [], "evidence": [], "why": None}}
        return nodes, edges, details

    node_ids = _collect_neighbors_at_depth(G, cid, depth)
    node_ids = _filter_by_focus(node_ids, G, focus, show_documents)
    node_ids = _limit_nodes(node_ids, G, cid, limit)

    # Add virtual CoachingAction nodes from recommendations
    tdr = bg.get_client_traits_drivers_risks(G, client_name)
    traits = [{"label": t.get("label"), "evidence": t.get("evidence")} for t in tdr.get("traits") or []]
    drivers = [{"label": d.get("label"), "evidence": d.get("evidence")} for d in tdr.get("drivers") or []]
    risks = [{"label": r.get("label"), "evidence": r.get("evidence")} for r in tdr.get("risks") or []]
    recs = rec.get_recommendations(traits, drivers, risks, max_n=5)
    action_nodes = {}
    for r in recs:
        aid = o.action_id(r.get("action", "")[:100])
        action_nodes[aid] = {
            "type": "action",
            "label": r.get("action", ""),
            "edges": [{"relation": "recommended_action", "target": client_name}],
            "evidence": [r.get("evidence") or {}],
            "why": r.get("why"),
        }
    if focus in (FOCUS_ALL, FOCUS_RECOMMENDATIONS):
        for aid in action_nodes:
            node_ids.add(aid)

    # Build node list for agraph (id, label, type for styling)
    type_to_color = {
        "client": "#2e7d32",
        "trait": "#1976d2",
        "driver": "#f57c00",
        "risk": "#c2185b",
        "action": "#00796b",
        "document": "#616161",
    }
    nodes_out = []
    details_map = {}
    for nid in node_ids:
        ntype = _node_type(nid, G) if G.has_node(nid) else ("action" if nid in action_nodes else "unknown")
        if nid in action_nodes:
            details_map[nid] = action_nodes[nid]
        else:
            details_map[nid] = get_node_details(G, nid)
        label = _get_label(G, nid) if G.has_node(nid) else (action_nodes.get(nid) or {}).get("label", str(nid)[:80])
        nodes_out.append({
            "id": str(nid),
            "label": label[:40] + "..." if len(label) > 40 else label,
            "type": ntype,
            "color": type_to_color.get(ntype, "#757575"),
        })

    # Edges: only between nodes we include
    edges_out = []
    for u, v, key in G.edges(keys=True):
        if u not in node_ids or v not in node_ids:
            continue
        rel = str(key) if key else "link"
        edges_out.append({"source": str(u), "target": str(v), "label": rel})
    for aid in action_nodes:
        if aid in node_ids and cid in node_ids:
            edges_out.append({"source": str(cid), "target": str(aid), "label": "recommended_action"})

    return nodes_out, edges_out, details_map


def graph_summary(G: nx.MultiDiGraph, client_name: str) -> Dict[str, Any]:
    """Node counts by type and top 3 most-connected traits/drivers."""
    cid = o.client_id(client_name)
    if not G.has_node(cid):
        return {"counts": {}, "top_traits": [], "top_drivers": []}
    counts = {"client": 0, "trait": 0, "driver": 0, "risk": 0, "document": 0, "action": 0}
    trait_degree = []
    driver_degree = []
    for nid in G.nodes():
        t = _node_type(nid, G)
        if t in counts:
            counts[t] = counts.get(t, 0) + 1
        if t == "trait":
            trait_degree.append((nid, G.degree(nid)))
        if t == "driver":
            driver_degree.append((nid, G.degree(nid)))
    trait_degree.sort(key=lambda x: -x[1])
    driver_degree.sort(key=lambda x: -x[1])
    top_traits = [_get_label(G, nid) for nid, _ in trait_degree[:3]]
    top_drivers = [_get_label(G, nid) for nid, _ in driver_degree[:3]]
    return {"counts": counts, "top_traits": top_traits, "top_drivers": top_drivers}
