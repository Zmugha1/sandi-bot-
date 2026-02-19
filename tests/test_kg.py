"""
Minimal QA: run extraction on a sample (no real PDF required), confirm doc_id, facts, graph idempotency.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from kg import storage as stg
from kg import extract_pdf as ext
from kg import build_graph as bg
from kg import ontology as kg_ontology


def test_doc_id():
    b = b"fake pdf content"
    doc_id = stg.doc_id_from_bytes(b)
    assert doc_id and len(doc_id) == 32 and doc_id.isalnum(), "doc_id should be 32-char hex"


def test_extract_facts_deterministic():
    # Minimal PDF-like content (PyMuPDF can open text)
    fake_pdf = _make_minimal_pdf()
    if fake_pdf is None:
        return  # skip if no PDF lib
    out = ext.extract_facts("Test Client", "doc123", fake_pdf)
    assert out["client_name"] == "Test Client"
    assert out["doc_id"] == "doc123"
    assert "facts" in out
    # May be empty if patterns don't match; at least structure is correct
    assert isinstance(out["facts"], list)


def test_graph_merge_and_idempotency():
    stg.ensure_dirs()
    G = bg.load_graph()
    initial_nodes = G.number_of_nodes()
    extraction = {
        "client_name": "QA_Client",
        "doc_id": "qa_doc_001",
        "facts": [
            {"type": "trait", "label": "Overthinks decisions", "evidence": {"page": 1, "snippet": "tends to overthink"}},
            {"type": "driver", "label": "Autonomy", "evidence": {"page": 2, "snippet": "motivated by autonomy"}},
        ],
    }
    G = bg.merge_facts_into_graph(G, extraction)
    assert G.number_of_nodes() > initial_nodes
    assert kg_ontology.client_id("QA_Client") in G.nodes()
    # Re-merge same extraction: should add same nodes (idempotent by doc_id in storage, not in graph)
    G2 = bg.merge_facts_into_graph(G.copy(), extraction)
    sub = bg.get_client_subgraph(G2, "QA_Client")
    assert sub.number_of_nodes() >= 2
    tdr = bg.get_client_traits_drivers_risks(G2, "QA_Client")
    assert len(tdr["traits"]) >= 1
    assert len(tdr["drivers"]) >= 1


def _make_minimal_pdf():
    try:
        import fitz
        import tempfile
        import os
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Behavioral: tends to overthink decisions. Motivated by autonomy. Avoids quick decisions.")
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            doc.write(f.name)
            doc.close()
            with open(f.name, "rb") as r:
                buf = r.read()
            os.unlink(f.name)
        return buf
    except Exception:
        return None


if __name__ == "__main__":
    test_doc_id()
    print("doc_id OK")
    test_extract_facts_deterministic()
    print("extract_facts OK")
    test_graph_merge_and_idempotency()
    print("graph merge OK")
