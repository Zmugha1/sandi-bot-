"""
Local persistence for extracted facts and graph.
Idempotent: same doc_id for a client does not duplicate facts/edges.
Per-client index: data/kg/index/<client_slug>.json tracks processed doc_ids.
"""
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# Base paths: always absolute so they work regardless of working directory
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = (REPO_ROOT / "data").resolve()
KG_DIR = (DATA_DIR / "kg").resolve()
INDEX_DIR = (KG_DIR / "index").resolve()
UPLOADS_DIR = (DATA_DIR / "uploads").resolve()
FACTS_JSONL = (KG_DIR / "facts.jsonl").resolve()
GRAPH_GRAPHML = (KG_DIR / "graph.graphml").resolve()


def _client_slug(name: str) -> str:
    s = "".join(c if c.isalnum() or c in " -_" else "" for c in (name or "").strip())
    return s.replace(" ", "_").replace("-", "_")[:64] or "unknown"


def ensure_dirs() -> None:
    KG_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def doc_id_from_bytes(pdf_bytes: bytes) -> str:
    """Consistent sha256 of raw uploaded bytes (full hash)."""
    return hashlib.sha256(pdf_bytes).hexdigest()


def get_client_index_path(client_slug: str) -> Path:
    return INDEX_DIR / f"{client_slug}.json"


def load_client_index(client_slug: str) -> Dict[str, Any]:
    """Load per-client index: { client_slug, processed_docs: { doc_id: { uploaded_pdf_path, processed_at, facts_count, graph_updated } } }."""
    path = get_client_index_path(client_slug)
    if not path.exists():
        return {"client_slug": client_slug, "processed_docs": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {"client_slug": client_slug, "processed_docs": {}}
    except Exception:
        return {"client_slug": client_slug, "processed_docs": {}}


def save_client_index(client_slug: str, index_data: Dict[str, Any]) -> None:
    ensure_dirs()
    path = get_client_index_path(client_slug)
    index_data["client_slug"] = client_slug
    if "processed_docs" not in index_data:
        index_data["processed_docs"] = {}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2, ensure_ascii=False)


def register_processed_doc(
    client_slug: str,
    client_display_name: str,
    doc_id: str,
    uploaded_pdf_path: str,
    facts_count: int,
    graph_updated: bool = True,
) -> None:
    """Record that this doc_id was processed for this client."""
    idx = load_client_index(client_slug)
    idx["processed_docs"][doc_id] = {
        "uploaded_pdf_path": uploaded_pdf_path,
        "processed_at": datetime.utcnow().isoformat() + "Z",
        "facts_count": facts_count,
        "graph_updated": graph_updated,
    }
    save_client_index(client_slug, idx)


def append_fact(fact: Dict[str, Any]) -> None:
    """Append one fact. Fact must include client_slug, client_display_name, doc_id, type, label, evidence."""
    ensure_dirs()
    with open(FACTS_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(fact, ensure_ascii=False) + "\n")


def load_facts_for_client(client_name: str, doc_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Load facts from JSONL. Filter by client (by client_name or client_slug derived from client_name).
    If doc_id given, only that doc; else all for client.
    """
    if not FACTS_JSONL.exists():
        return []
    slug = _client_slug(client_name)
    out = []
    with open(FACTS_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                # Match by client_name or client_slug (backward compat: old rows may only have client_name)
                obj_slug = obj.get("client_slug") or _client_slug(obj.get("client_name") or "")
                obj_name = (obj.get("client_name") or obj.get("client_display_name") or "").strip()
                name_match = (obj_name == client_name.strip()) or (obj_slug == slug)
                if not name_match:
                    continue
                if doc_id is not None and obj.get("doc_id") != doc_id:
                    continue
                out.append(obj)
            except json.JSONDecodeError:
                continue
    return out


def client_has_doc_id(client_name: str, doc_id: str) -> bool:
    """
    Return True only if this doc_id is in the client's index (already processed).
    Ensures we only show "already processed" when we actually have a record for this client+doc.
    """
    slug = _client_slug(client_name)
    idx = load_client_index(slug)
    return doc_id in (idx.get("processed_docs") or {})


def save_upload(client_slug: str, filename: str, pdf_bytes: bytes) -> Path:
    """Save PDF under data/uploads/<client_slug>/<timestamp>_<filename>.pdf."""
    ensure_dirs()
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


def get_paths_for_debug() -> Dict[str, Any]:
    """Return absolute paths and existence for Debug Panel."""
    ensure_dirs()
    return {
        "cwd": str(Path.cwd()),
        "repo_root": str(REPO_ROOT),
        "uploads_dir": str(UPLOADS_DIR),
        "uploads_exists": UPLOADS_DIR.exists(),
        "index_dir": str(INDEX_DIR),
        "index_exists": INDEX_DIR.exists(),
        "facts_path": str(FACTS_JSONL),
        "facts_exists": FACTS_JSONL.exists(),
        "facts_size": FACTS_JSONL.stat().st_size if FACTS_JSONL.exists() else 0,
        "graph_path": str(GRAPH_GRAPHML),
        "graph_exists": GRAPH_GRAPHML.exists(),
        "graph_size": GRAPH_GRAPHML.stat().st_size if GRAPH_GRAPHML.exists() else 0,
    }
