"""
Local persistence for extracted facts and graph.
Idempotent: same doc_id for a client does not duplicate facts/edges.
"""
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional

# Base paths relative to repo root (sandi-bot)
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
KG_DIR = DATA_DIR / "kg"
UPLOADS_DIR = DATA_DIR / "uploads"
FACTS_JSONL = KG_DIR / "facts.jsonl"
GRAPH_GRAPHML = KG_DIR / "graph.graphml"


def ensure_dirs() -> None:
    KG_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def doc_id_from_bytes(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()[:32]


def append_fact(fact: Dict[str, Any]) -> None:
    ensure_dirs()
    with open(FACTS_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(fact, ensure_ascii=False) + "\n")


def load_facts_for_client(client_name: str, doc_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load facts from JSONL. If doc_id given, only that doc; else all for client."""
    if not FACTS_JSONL.exists():
        return []
    out = []
    with open(FACTS_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("client_name") != client_name:
                    continue
                if doc_id is not None and obj.get("doc_id") != doc_id:
                    continue
                out.append(obj)
            except json.JSONDecodeError:
                continue
    return out


def client_has_doc_id(client_name: str, doc_id: str) -> bool:
    """Return True if we already have facts for this client+doc_id (idempotency)."""
    facts = load_facts_for_client(client_name, doc_id=doc_id)
    return len(facts) > 0


def save_upload(client_slug: str, filename: str, pdf_bytes: bytes) -> Path:
    """Save PDF under data/uploads/<client_slug>/<timestamp>_<filename>.pdf."""
    ensure_dirs()
    from datetime import datetime
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)[:80]
    sub = UPLOADS_DIR / client_slug
    sub.mkdir(parents=True, exist_ok=True)
    path = sub / f"{ts}_{safe_name}"
    path.write_bytes(pdf_bytes)
    return path


def get_graph_path() -> Path:
    ensure_dirs()
    return GRAPH_GRAPHML


def get_facts_path() -> Path:
    ensure_dirs()
    return FACTS_JSONL
