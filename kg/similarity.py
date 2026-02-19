"""
Similar clients: deterministic TF-IDF over traits + drivers + risks.
Optional sentence-transformers (OFF by default). Cache embeddings under data/kg/embeddings.pkl.
"""
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from . import storage as stg

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = REPO_ROOT / "data" / "clients_seed.json"
CACHE_PATH = stg.KG_DIR / "embeddings.pkl"

_USE_EMBEDDINGS = False  # Set True to use sentence-transformers when available


def _load_seed_clients() -> List[Dict[str, Any]]:
    if not SEED_PATH.exists():
        return []
    with open(SEED_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def _text_for_client(client: Dict[str, Any]) -> str:
    parts = []
    for k in ("traits", "drivers", "risks"):
        vals = client.get(k) or []
        if isinstance(vals, list):
            parts.extend(str(v) for v in vals)
        else:
            parts.append(str(vals))
    return " ".join(parts).lower()


def _text_from_facts(traits: List[Dict], drivers: List[Dict], risks: List[Dict]) -> str:
    parts = []
    for d in (traits or []) + (drivers or []) + (risks or []):
        label = d.get("label") or d.get("label", "")
        if label:
            parts.append(label.lower())
    return " ".join(parts)


def similar_clients_tfidf(
    client_traits: List[Dict],
    client_drivers: List[Dict],
    client_risks: List[Dict],
    seed_clients: Optional[List[Dict]] = None,
    top_n: int = 5,
) -> List[Tuple[Dict[str, Any], float, List[str]]]:
    """
    Returns list of (seed_client, score, overlap_explanations).
    Deterministic TF-IDF cosine similarity. No LLM.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        return []

    seed = seed_clients or _load_seed_clients()
    if not seed:
        return []

    query_text = _text_from_facts(client_traits, client_drivers, client_risks)
    if not query_text.strip():
        return []

    seed_texts = [_text_for_client(c) for c in seed]
    all_texts = [query_text] + seed_texts
    vectorizer = TfidfVectorizer(max_features=200, stop_words="english", ngram_range=(1, 2))
    try:
        X = vectorizer.fit_transform(all_texts)
    except Exception:
        return []

    q_vec = X[0:1]
    seed_vecs = X[1:]
    sims = cosine_similarity(q_vec, seed_vecs).ravel()

    query_words = set(query_text.split())
    results = []
    for i, (sclient, sim) in enumerate(zip(seed, sims)):
        if sim <= 0:
            continue
        stext = _text_for_client(sclient)
        overlap = query_words & set(stext.split())
        overlap_explanation = list(overlap)[:5] if overlap else ["similar profile"]
        results.append((sclient, float(sim), overlap_explanation))

    results.sort(key=lambda x: -x[1])
    return results[:top_n]


# Optional: sentence-transformers path (not used by default)
def similar_clients_embeddings(
    client_traits: List[Dict],
    client_drivers: List[Dict],
    client_risks: List[Dict],
    top_n: int = 5,
) -> List[Tuple[Dict[str, Any], float, List[str]]]:
    """Optional: use sentence-transformers. OFF by default."""
    if not _USE_EMBEDDINGS:
        return similar_clients_tfidf(client_traits, client_drivers, client_risks, top_n=top_n)
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return similar_clients_tfidf(client_traits, client_drivers, client_risks, top_n=top_n)

    seed = _load_seed_clients()
    if not seed:
        return []
    query_text = _text_from_facts(client_traits, client_drivers, client_risks)
    if not query_text.strip():
        return []

    model = SentenceTransformer("all-MiniLM-L6-v2")
    q_emb = model.encode([query_text])
    seed_texts = [_text_for_client(c) for c in seed]
    seed_embs = model.encode(seed_texts)
    from sklearn.metrics.pairwise import cosine_similarity
    sims = cosine_similarity(q_emb, seed_embs).ravel()
    query_words = set(query_text.split())
    results = []
    for i, (sclient, sim) in enumerate(zip(seed, sims)):
        if sim <= 0:
            continue
        stext = _text_for_client(sclient)
        overlap = query_words & set(stext.split())
        overlap_explanation = list(overlap)[:5] if overlap else ["similar profile"]
        results.append((sclient, float(sim), overlap_explanation))
    results.sort(key=lambda x: -x[1])
    return results[:top_n]


def get_similar_clients(
    client_traits: List[Dict],
    client_drivers: List[Dict],
    client_risks: List[Dict],
    top_n: int = 5,
) -> List[Tuple[Dict[str, Any], float, List[str]]]:
    """Public API: deterministic TF-IDF by default."""
    return similar_clients_tfidf(client_traits, client_drivers, client_risks, top_n=top_n)
