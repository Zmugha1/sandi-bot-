"""
Knowledge Graph ontology: node types and edge types.
Deterministic; no LLM.
"""

# Node type prefixes for NetworkX
NODE_CLIENT = "Client"
NODE_TRAIT = "Trait"
NODE_DRIVER = "Driver"
NODE_RISK = "Risk"
NODE_COACHING_ACTION = "CoachingAction"
NODE_DOCUMENT = "Document"

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
    return f"{NODE_CLIENT}:{_slug(name)}"


def trait_id(label: str) -> str:
    return f"{NODE_TRAIT}:{_norm_label(label)}"


def driver_id(label: str) -> str:
    return f"{NODE_DRIVER}:{_norm_label(label)}"


def risk_id(label: str) -> str:
    return f"{NODE_RISK}:{_norm_label(label)}"


def action_id(label: str) -> str:
    return f"{NODE_COACHING_ACTION}:{_norm_label(label)}"


def document_id(doc_id: str) -> str:
    return f"{NODE_DOCUMENT}:{doc_id}"


def _slug(name: str) -> str:
    s = "".join(c if c.isalnum() or c in " -_" else "" for c in (name or "").strip())
    return s.replace(" ", "_").replace("-", "_")[:64] or "unknown"


def _norm_label(label: str) -> str:
    return (label or "").strip()[:200] or "unknown"
