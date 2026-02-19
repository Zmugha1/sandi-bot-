"""
Knowledge Graph Streamlit page: upload PDF, extract insights, show graph and recommendations.
Minimal UI, no icons. Deterministic by default.
"""
import streamlit as st
from pathlib import Path

# Ensure repo root on path
REPO_ROOT = Path(__file__).resolve().parent.parent
import sys
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kg import storage as stg
from kg import extract_pdf as ext
from kg import build_graph as bg
from kg import ontology as kg_ontology
from kg import similarity as sim
from kg import recommendations as rec
from kg import strategy_advisor as advisor


def _client_slug(name: str) -> str:
    return "".join(c if c.isalnum() or c in " -_" else "" for c in (name or "").strip()).replace(" ", "_").replace("-", "_")[:64] or "client"


def render():
    st.title("Knowledge Graph")
    st.caption("Upload a personality report PDF, then build insights. All recommendations cite evidence from the document.")

    # Section A: Upload + Client Details
    st.subheader("Upload and client details")
    pdf_file = st.file_uploader("Personality Report (PDF)", type=["pdf"], key="kg_pdf")
    client_name = st.text_input("Client Name", value="", key="kg_client_name", placeholder="Required")
    business_type = st.selectbox(
        "Business Type (optional)",
        ["", "IT Services", "Healthcare Consulting", "Financial Advisory", "Marketing Agency", "Legal Services", "Other"],
        key="kg_business_type",
    )
    build_clicked = st.button("Build Insights", type="primary", key="kg_build")

    extraction = None
    current_client = (client_name or "").strip()
    if build_clicked and pdf_file is not None and current_client:
        with st.spinner("Extracting insights..."):
            pdf_bytes = pdf_file.read()
            doc_id = stg.doc_id_from_bytes(pdf_bytes)
            if stg.client_has_doc_id(current_client, doc_id):
                st.info("This report was already processed for this client. No duplicate facts added.")
            else:
                extraction = ext.extract_facts(current_client, doc_id, pdf_bytes)
                stg.ensure_dirs()
                for fact in extraction.get("facts") or []:
                    row = {
                        "client_name": current_client,
                        "doc_id": doc_id,
                        "type": fact.get("type"),
                        "label": fact.get("label"),
                        "evidence": fact.get("evidence"),
                    }
                    stg.append_fact(row)
                G = bg.load_graph()
                G = bg.merge_facts_into_graph(G, extraction)
                bg.save_graph(G)
                save_path = stg.save_upload(_client_slug(current_client), pdf_file.name, pdf_bytes)
                st.success(f"Processed {len(extraction.get('facts') or [])} insights. Saved to {save_path.name}.")
            extraction = ext.extract_facts(current_client, doc_id, pdf_bytes)
    elif build_clicked and not current_client:
        st.warning("Please enter a client name.")
    elif build_clicked and pdf_file is None:
        st.warning("Please upload a PDF.")

    # If we have a client (from form or session), load their insights from graph
    if not extraction and current_client:
        G = bg.load_graph()
        if G.has_node(kg_ontology.client_id(current_client)):
            extraction = {
                "client_name": current_client,
                "doc_id": "",
                "facts": [],
            }
            tdr = bg.get_client_traits_drivers_risks(G, current_client)
            for item in tdr.get("traits") or []:
                extraction["facts"].append({"type": "trait", "label": item.get("label"), "evidence": item.get("evidence")})
            for item in tdr.get("drivers") or []:
                extraction["facts"].append({"type": "driver", "label": item.get("label"), "evidence": item.get("evidence")})
            for item in tdr.get("risks") or []:
                extraction["facts"].append({"type": "risk", "label": item.get("label"), "evidence": item.get("evidence")})

    if extraction:
        traits = [f for f in extraction.get("facts") or [] if f.get("type") == "trait"]
        drivers = [f for f in extraction.get("facts") or [] if f.get("type") == "driver"]
        risks = [f for f in extraction.get("facts") or [] if f.get("type") in ("risk", "communication_dont")]
        comm_do = [f for f in extraction.get("facts") or [] if f.get("type") in ("communication_do",)]

        # Section B: Key Insights (with evidence)
        st.subheader("Key insights")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**Traits**")
            for t in traits[:15]:
                ev = t.get("evidence") or {}
                st.markdown(f"- {t.get('label', '')}")
                st.caption(f"p.{ev.get('page', '?')}: {ev.get('snippet', '')[:100]}...")
        with col2:
            st.markdown("**Drivers**")
            for d in drivers[:15]:
                ev = d.get("evidence") or {}
                st.markdown(f"- {d.get('label', '')}")
                st.caption(f"p.{ev.get('page', '?')}: {ev.get('snippet', '')[:100]}...")
        with col3:
            st.markdown("**Risks / Watch**")
            for r in risks[:15]:
                ev = r.get("evidence") or {}
                st.markdown(f"- {r.get('label', '')}")
                st.caption(f"p.{ev.get('page', '?')}: {ev.get('snippet', '')[:100]}...")

        # Section C: Recommendations (with why)
        st.subheader("Recommendations")
        recs = rec.get_recommendations(traits, drivers, risks, max_n=5)
        if recs:
            for r in recs:
                st.markdown(f"**{r.get('action', '')}**")
                st.markdown(f"Why: {r.get('why', '')}")
                ev = r.get("evidence") or {}
                st.caption(f"Evidence (p.{ev.get('page', '?')}): {ev.get('snippet', '')[:120]}...")
                st.markdown("---")
        else:
            st.caption("No rules matched. Add rules in data/rules.yaml or add more traits/drivers/risks from the PDF.")

        # Strategy Advisor (uses graph context only; never invents)
        st.subheader("Strategy Advisor")
        st.caption("Ask a coaching question. Answers use only this client's traits, drivers, and risks from the graph.")
        advisor_question = st.text_input("Your question", value="", key="kg_advisor_q", placeholder="e.g. How should I approach them? What's the main risk?")
        if st.button("Get advice", key="kg_advisor_btn") and advisor_question.strip():
            ctx = {
                "client_name": current_client,
                "traits": [{"label": t.get("label"), "evidence": t.get("evidence")} for t in traits],
                "drivers": [{"label": d.get("label"), "evidence": d.get("evidence")} for d in drivers],
                "risks": [{"label": r.get("label"), "evidence": r.get("evidence")} for r in risks],
            }
            result = advisor.advise(ctx, advisor_question.strip())
            st.session_state["kg_advisor_result"] = result
            st.session_state["kg_advisor_question"] = advisor_question.strip()
        if st.session_state.get("kg_advisor_result"):
            result = st.session_state["kg_advisor_result"]
            if st.session_state.get("kg_advisor_question"):
                st.caption(f"Question: {st.session_state['kg_advisor_question']}")
            st.markdown("**1. Recommendation**")
            st.markdown(result.get("recommendation", ""))
            st.markdown("**2. Why**")
            st.markdown(result.get("why", "") or "—")
            st.markdown("**3. Signals still missing**")
            missing = result.get("signals_still_missing") or []
            if missing:
                for m in missing:
                    st.markdown(f"- {m}")
            else:
                st.markdown("—")
            st.markdown("**4. Suggested next step**")
            st.markdown(result.get("suggested_next_step", ""))

        # Section D: Similar Clients
        st.subheader("Similar clients")
        similar = sim.get_similar_clients(traits, drivers, risks, top_n=5)
        if similar:
            for sclient, score, overlap in similar:
                st.markdown(f"**{sclient.get('name', '')}** — {sclient.get('business_type', '')}")
                st.caption(f"Similarity: {score:.2f}. Overlap: {', '.join(overlap[:5])}.")
        else:
            st.caption("No similar clients in seed set. Add entries to data/clients_seed.json.")

        # Section E: Graph View
        st.subheader("Graph view")
        G = bg.load_graph()
        sub = bg.get_client_subgraph(G, current_client)
        if sub and sub.number_of_nodes() > 0:
            try:
                from pyvis.network import Network
                net = Network(height="400px", width="100%", directed=True)
                for n in sub.nodes():
                    label = sub.nodes[n].get("label", n)
                    net.add_node(n, label=label[:30], title=label)
                for u, v, _ in sub.edges(keys=True):
                    net.add_edge(u, v)
                html = net.generate_html()
                st.components.v1.html(html, height=420, scrolling=False)
            except Exception:
                _fallback_graph_view(traits, drivers, risks)
        else:
            _fallback_graph_view(traits, drivers, risks)
    else:
        st.caption("Upload a PDF and enter a client name, then click Build Insights.")


def _fallback_graph_view(traits, drivers, risks):
    st.markdown("**Key traits**")
    for t in traits[:10]:
        st.markdown(f"- {t.get('label', '')}")
    st.markdown("**Key drivers**")
    for d in drivers[:10]:
        st.markdown(f"- {d.get('label', '')}")
    st.markdown("**Key risks**")
    for r in risks[:10]:
        st.markdown(f"- {r.get('label', '')}")
