"""
Build/update NetworkX MultiDiGraph from extracted facts.
Stores provenance (doc_id, page, snippet) on edges. Idempotent per doc_id.
"""
import networkx as nx
from typing import Dict, Any, List, Optional

from . import ontology as o
from . import storage as stg


def _add_fact_to_graph(G: nx.MultiDiGraph, client_name: str, doc_id: str, fact: Dict[str, Any], confidence: float = o.DEFAULT_CONFIDENCE) -> None:
    cid = o.client_id(client_name)
    did = o.document_id(doc_id)
    ev = fact.get("evidence") or {}
    page = ev.get("page", 0)
    snippet = ev.get("snippet", "")[:300]

    G.add_node(cid, node_type=o.NODE_CLIENT, label=client_name)
    G.add_node(did, node_type=o.NODE_DOCUMENT, label=doc_id)

    fact_type = fact.get("type", "trait")
    label = (fact.get("label") or "").strip()[:200] or "unknown"

    if fact_type == "trait":
        nid = o.trait_id(label)
        G.add_node(nid, node_type=o.NODE_TRAIT, label=label)
        G.add_edge(cid, nid, key=o.EDGE_HAS_TRAIT, doc_id=doc_id, page=page, snippet=snippet, confidence=confidence)
    elif fact_type == "driver":
        nid = o.driver_id(label)
        G.add_node(nid, node_type=o.NODE_DRIVER, label=label)
        G.add_edge(cid, nid, key=o.EDGE_HAS_DRIVER, doc_id=doc_id, page=page, snippet=snippet, confidence=confidence)
    elif fact_type in ("risk", "communication_dont"):
        nid = o.risk_id(label)
        G.add_node(nid, node_type=o.NODE_RISK, label=label)
        G.add_edge(cid, nid, key=o.EDGE_HAS_RISK, doc_id=doc_id, page=page, snippet=snippet, confidence=confidence)
    elif fact_type in ("communication_do",):
        # Store as trait for graph simplicity
        nid = o.trait_id("Do: " + label)
        G.add_node(nid, node_type=o.NODE_TRAIT, label="Do: " + label)
        G.add_edge(cid, nid, key=o.EDGE_HAS_TRAIT, doc_id=doc_id, page=page, snippet=snippet, confidence=confidence)

    G.add_edge(cid, did, key=o.EDGE_EVIDENCE_FROM, doc_id=doc_id, page=page, snippet=snippet, confidence=confidence)


def load_graph() -> nx.MultiDiGraph:
    path = stg.get_graph_path()
    if path.exists():
        try:
            return nx.read_graphml(path, create_using=nx.MultiDiGraph())
        except Exception:
            pass
    return nx.MultiDiGraph()


def save_graph(G: nx.MultiDiGraph) -> None:
    path = stg.get_graph_path()
    nx.write_graphml(G, path)


def merge_facts_into_graph(G: nx.MultiDiGraph, extraction: Dict[str, Any], confidence: float = o.DEFAULT_CONFIDENCE) -> nx.MultiDiGraph:
    client_name = extraction.get("client_name") or ""
    doc_id = extraction.get("doc_id") or ""
    for fact in extraction.get("facts") or []:
        _add_fact_to_graph(G, client_name, doc_id, fact, confidence=confidence)
    return G


def get_client_subgraph(G: nx.MultiDiGraph, client_name: str) -> nx.MultiDiGraph:
    """Induced subgraph: client node + all neighbors + edges between them."""
    cid = o.client_id(client_name)
    if not G.has_node(cid):
        return nx.MultiDiGraph()
    succ = set(G.successors(cid))
    pred = set(G.predecessors(cid))
    nodes = {cid} | succ | pred
    return G.subgraph(nodes).copy()


def get_client_traits_drivers_risks(G: nx.MultiDiGraph, client_name: str) -> Dict[str, List[Dict[str, Any]]]:
    """Return {"traits": [...], "drivers": [...], "risks": [...]} with label and evidence."""
    cid = o.client_id(client_name)
    out = {"traits": [], "drivers": [], "risks": []}
    if not G.has_node(cid):
        return out
    for u, v, key, data in G.edges(data=True, keys=True):
        if u != cid:
            continue
        if key == o.EDGE_HAS_TRAIT:
            label = G.nodes[v].get("label", "")
            out["traits"].append({"label": label, "evidence": {"page": data.get("page"), "snippet": data.get("snippet", "")}})
        elif key == o.EDGE_HAS_DRIVER:
            label = G.nodes[v].get("label", "")
            out["drivers"].append({"label": label, "evidence": {"page": data.get("page"), "snippet": data.get("snippet", "")}})
        elif key == o.EDGE_HAS_RISK:
            label = G.nodes[v].get("label", "")
            out["risks"].append({"label": label, "evidence": {"page": data.get("page"), "snippet": data.get("snippet", "")}})
    return out
