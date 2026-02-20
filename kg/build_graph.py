"""
Build/update NetworkX MultiDiGraph from extracted facts.
Stores provenance (doc_id, page, snippet) on edges. Idempotent per doc_id.
Node IDs: client:<slug>, trait:<label>, driver:<label>, risk:<label>, doc:<doc_id>.
"""
import networkx as nx
from typing import Dict, Any, List, Optional

from . import ontology as o
from . import storage as stg


def _normalize_node_id(nid: str) -> str:
    """Normalize legacy GraphML node ids to standard form (e.g. Client: -> client:)."""
    if not nid or ":" not in nid:
        return nid
    prefix, rest = nid.split(":", 1)
    lower = prefix.strip().lower()
    if lower == "client":
        return f"client:{rest}"
    if lower == "trait":
        return f"trait:{rest}"
    if lower == "driver":
        return f"driver:{rest}"
    if lower == "risk":
        return f"risk:{rest}"
    if lower in ("coachingaction", "action"):
        return f"action:{rest}"
    if lower == "document" or lower == "doc":
        return f"doc:{rest}"
    return nid


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

    # Store relation on edge so GraphML round-trip preserves type (keys can become 0,1,2...)
    if fact_type in ("trait", "strengths_do", "communication_do", "trait_do"):
        nid = o.trait_id(label)
        G.add_node(nid, node_type=o.NODE_TRAIT, label=label)
        G.add_edge(cid, nid, key=o.EDGE_HAS_TRAIT, relation=o.EDGE_HAS_TRAIT, doc_id=doc_id, page=page, snippet=snippet, confidence=confidence)
    elif fact_type == "driver":
        nid = o.driver_id(label)
        G.add_node(nid, node_type=o.NODE_DRIVER, label=label)
        G.add_edge(cid, nid, key=o.EDGE_HAS_DRIVER, relation=o.EDGE_HAS_DRIVER, doc_id=doc_id, page=page, snippet=snippet, confidence=confidence)
    elif fact_type in ("risk", "communication_dont", "risks_dont", "trait_dont"):
        nid = o.risk_id(label)
        G.add_node(nid, node_type=o.NODE_RISK, label=label)
        G.add_edge(cid, nid, key=o.EDGE_HAS_RISK, relation=o.EDGE_HAS_RISK, doc_id=doc_id, page=page, snippet=snippet, confidence=confidence)

    G.add_edge(cid, did, key=o.EDGE_EVIDENCE_FROM, relation=o.EDGE_EVIDENCE_FROM, doc_id=doc_id, page=page, snippet=snippet, confidence=confidence)


def load_graph() -> nx.MultiDiGraph:
    path = stg.get_graph_path()
    if path.exists():
        try:
            G = nx.read_graphml(path, create_using=nx.MultiDiGraph())
            # Normalize legacy node ids so lookups by client_id() etc. match
            if G.number_of_nodes() > 0:
                mapping = {}
                for nid in list(G.nodes()):
                    new_id = _normalize_node_id(str(nid))
                    if new_id != nid:
                        mapping[nid] = new_id
                if mapping:
                    G = nx.relabel_nodes(G, mapping, copy=True)
                for nid in G.nodes():
                    nt = G.nodes[nid].get("node_type")
                    if isinstance(nt, str):
                        lower = nt.strip().lower()
                        if lower in ("client", "trait", "driver", "risk", "document", "doc", "coachingaction", "action"):
                            G.nodes[nid]["node_type"] = "client" if lower == "client" else "trait" if lower == "trait" else "driver" if lower == "driver" else "risk" if lower == "risk" else "doc" if lower in ("document", "doc") else "action"
            if G.number_of_nodes() == 0 and stg.FACTS_JSONL.exists():
                G = rebuild_graph_from_facts()
            return G
        except Exception:
            pass
    G = nx.MultiDiGraph()
    if stg.FACTS_JSONL.exists():
        return rebuild_graph_from_facts()
    return G


def rebuild_graph_from_facts() -> nx.MultiDiGraph:
    """Build graph from all facts in facts.jsonl. Use when graph is empty but facts exist."""
    G = nx.MultiDiGraph()
    if not stg.FACTS_JSONL.exists():
        return G
    import json
    # Group facts by (client_name, doc_id)
    groups = {}
    with open(stg.FACTS_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            client_name = (obj.get("client_display_name") or obj.get("client_name") or "").strip()
            if not client_name:
                continue
            doc_id = obj.get("doc_id") or ""
            key = (client_name, doc_id)
            if key not in groups:
                groups[key] = {"client_name": client_name, "doc_id": doc_id, "facts": []}
            groups[key]["facts"].append(obj)
    for (_, _), payload in groups.items():
        extraction = {
            "client_name": payload["client_name"],
            "doc_id": payload["doc_id"],
            "facts": payload["facts"],
        }
        G = merge_facts_into_graph(G, extraction)
    return G


def save_graph(G: nx.MultiDiGraph) -> None:
    path = stg.get_graph_path()
    nx.write_graphml(G, path)


def merge_facts_into_graph(G: nx.MultiDiGraph, extraction: Dict[str, Any], confidence: float = o.DEFAULT_CONFIDENCE) -> nx.MultiDiGraph:
    client_name = extraction.get("client_name") or ""
    doc_id = extraction.get("doc_id") or ""
    cid = o.client_id(client_name)
    did = o.document_id(doc_id)
    G.add_node(cid, node_type=o.NODE_CLIENT, label=client_name)
    G.add_node(did, node_type=o.NODE_DOCUMENT, label=doc_id)
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
        # After GraphML read, key can be 0,1,2; use relation attribute, else infer from target node type
        rel = data.get("relation") or (key if isinstance(key, str) else None)
        if not rel and G.has_node(v):
            nt = str(G.nodes[v].get("node_type") or "")
            if nt == o.NODE_TRAIT:
                rel = o.EDGE_HAS_TRAIT
            elif nt == o.NODE_DRIVER:
                rel = o.EDGE_HAS_DRIVER
            elif nt == o.NODE_RISK:
                rel = o.EDGE_HAS_RISK
        if rel == o.EDGE_HAS_TRAIT:
            label = G.nodes[v].get("label", "")
            out["traits"].append({"label": label, "evidence": {"page": data.get("page"), "snippet": data.get("snippet", "")}})
        elif rel == o.EDGE_HAS_DRIVER:
            label = G.nodes[v].get("label", "")
            out["drivers"].append({"label": label, "evidence": {"page": data.get("page"), "snippet": data.get("snippet", "")}})
        elif rel == o.EDGE_HAS_RISK:
            label = G.nodes[v].get("label", "")
            out["risks"].append({"label": label, "evidence": {"page": data.get("page"), "snippet": data.get("snippet", "")}})
    return out
