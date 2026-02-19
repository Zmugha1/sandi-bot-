"""
Knowledge Graph ontology: node types and edge types.
Deterministic; no LLM.
Node IDs: client:<slug>, trait:<label>, driver:<label>, risk:<label>, action:<label>, doc:<doc_id>.
"""

# Node type prefixes for NetworkX (display / GraphML node_type attribute)
NODE_CLIENT = "client"
NODE_TRAIT = "trait"
NODE_DRIVER = "driver"
NODE_RISK = "risk"
NODE_COACHING_ACTION = "action"
NODE_DOCUMENT = "doc"

# Edge types (relation names)
EDGE_HAS_TRAIT = "has_trait"
EDGE_HAS_DRIVER = "has_driver"
EDGE_HAS_RISK = "has_risk"
EDGE_EVIDENCE_FROM = "evidence_from"
EDGE_RECOMMENDED_ACTION = "recommended_action"

# Provenance keys stored on edges
ATTR_DOC_ID = "doc_id"
ATTR_PAGE = "page"
ATTR_SNIPPET = "snippet"
ATTR_WHY = "why"
ATTR_CONFIDENCE = "confidence"

DEFAULT_CONFIDENCE = 0.8


def client_id(name: str) -> str:
    """Standardized client node id: client:<client_slug>."""
    return f"client:{_slug(name)}"


def trait_id(label: str) -> str:
    """Standardized trait node id: trait:<normalized_label>."""
    return f"trait:{_norm_label(label)}"


def driver_id(label: str) -> str:
    """Standardized driver node id: driver:<normalized_label>."""
    return f"driver:{_norm_label(label)}"


def risk_id(label: str) -> str:
    """Standardized risk node id: risk:<normalized_label>."""
    return f"risk:{_norm_label(label)}"


def action_id(label: str) -> str:
    """Standardized action node id: action:<normalized_label>."""
    return f"action:{_norm_label(label)}"


def document_id(doc_id: str) -> str:
    """Standardized document node id: doc:<doc_id>."""
    return f"doc:{doc_id}"


def _slug(name: str) -> str:
    s = "".join(c if c.isalnum() or c in " -_" else "" for c in (name or "").strip())
    return s.replace(" ", "_").replace("-", "_")[:64] or "unknown"


def _norm_label(label: str) -> str:
    return (label or "").strip()[:200] or "unknown"
