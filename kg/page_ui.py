"""
Knowledge Graph Streamlit page: upload PDF, extract insights, show graph and recommendations.
Minimal UI, no icons. Deterministic by default.
"""
import streamlit as st
from pathlib import Path
from typing import Optional

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
from kg import visualize as viz


def _client_slug(name: str) -> str:
    return "".join(c if c.isalnum() or c in " -_" else "" for c in (name or "").strip()).replace(" ", "_").replace("-", "_")[:64] or "client"


def _build_debug_info(client_name: str, doc_id: str, extraction: Optional[dict], G, pdf_bytes: Optional[bytes]) -> dict:
    facts = extraction.get("facts") or [] if extraction else []
    by_type = {}
    for f in facts:
        t = f.get("type") or "unknown"
        by_type[t] = by_type.get(t, 0) + 1
    node_counts = {}
    for nid in G.nodes():
        nt = str(G.nodes[nid].get("node_type") or "unknown")
        node_counts[nt] = node_counts.get(nt, 0) + 1
    paths = stg.get_paths_for_debug()
    return {
        "client_name": client_name,
        "doc_id": doc_id,
        "pdf_pages": len(ext.extract_text_by_page(pdf_bytes)) if pdf_bytes else 0,
        "facts_extracted_count": len(facts),
        "facts_by_type": by_type,
        "graph_node_count": G.number_of_nodes(),
        "graph_edge_count": G.number_of_edges(),
        "graph_nodes_by_type": node_counts,
        "paths": paths,
    }


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
    debug_info = {}

    if build_clicked and pdf_file is not None and current_client:
        with st.spinner("Extracting insights..."):
            pdf_bytes = pdf_file.read()
            doc_id = stg.doc_id_from_bytes(pdf_bytes)
            # 1) Save upload first (so file exists regardless of idempotency)
            stg.ensure_dirs()
            save_path = stg.save_upload(_client_slug(current_client), pdf_file.name, pdf_bytes)
            # 2) Extract (for new doc) or load from graph (idempotency)
            if stg.client_has_doc_id(current_client, doc_id):
                st.info("This report was already processed for this client. No duplicate facts added. Loading from graph.")
                G = bg.load_graph()
                tdr = bg.get_client_traits_drivers_risks(G, current_client)
                extraction = {"client_name": current_client, "doc_id": doc_id, "facts": []}
                for item in tdr.get("traits") or []:
                    extraction["facts"].append({"type": "trait", "label": item.get("label"), "evidence": item.get("evidence")})
                for item in tdr.get("drivers") or []:
                    extraction["facts"].append({"type": "driver", "label": item.get("label"), "evidence": item.get("evidence")})
                for item in tdr.get("risks") or []:
                    extraction["facts"].append({"type": "risk", "label": item.get("label"), "evidence": item.get("evidence")})
                debug_info = _build_debug_info(current_client, doc_id, extraction, G, pdf_bytes)
            else:
                extraction = ext.extract_facts(current_client, doc_id, pdf_bytes)
                pdf_pages = len(ext.extract_text_by_page(pdf_bytes)) if extraction else 0
                # 3) Persist facts
                for fact in extraction.get("facts") or []:
                    row = {"client_name": current_client, "doc_id": doc_id, "type": fact.get("type"), "label": fact.get("label"), "evidence": fact.get("evidence")}
                    stg.append_fact(row)
                # 4) Update graph and persist
                G = bg.load_graph()
                G = bg.merge_facts_into_graph(G, extraction)
                bg.save_graph(G)
                _cached_load_graph.clear()
                _cached_agraph_elements.clear()
                debug_info = _build_debug_info(current_client, doc_id, extraction, G, pdf_bytes)
                st.success(f"Processed {len(extraction.get('facts') or [])} insights. Saved to {save_path.name}.")
    elif build_clicked and not current_client:
        st.warning("Please enter a client name.")
    elif build_clicked and pdf_file is None:
        st.warning("Please upload a PDF.")

    # Debug Panel (show when we have a client or after build)
    if current_client or debug_info:
        G_debug = _cached_load_graph()
        if not debug_info and current_client and G_debug.has_node(kg_ontology.client_id(current_client)):
            tdr = bg.get_client_traits_drivers_risks(G_debug, current_client)
            extraction_for_debug = {"client_name": current_client, "doc_id": "", "facts": []}
            for item in tdr.get("traits") or []:
                extraction_for_debug["facts"].append({"type": "trait", "label": item.get("label"), "evidence": item.get("evidence")})
            for item in tdr.get("drivers") or []:
                extraction_for_debug["facts"].append({"type": "driver", "label": item.get("label"), "evidence": item.get("evidence")})
            for item in tdr.get("risks") or []:
                extraction_for_debug["facts"].append({"type": "risk", "label": item.get("label"), "evidence": item.get("evidence")})
            debug_info = _build_debug_info(current_client, "", extraction_for_debug, G_debug, None)
        if debug_info:
            with st.expander("Debug Panel"):
                st.write("**Client:**", debug_info.get("client_name", "—"))
                st.write("**doc_id:**", debug_info.get("doc_id", "—"))
                st.write("**PDF pages:**", debug_info.get("pdf_pages", "—"))
                st.write("**Facts extracted:**", debug_info.get("facts_extracted_count", 0), "by type:", debug_info.get("facts_by_type", {}))
                st.write("**Graph nodes:**", debug_info.get("graph_node_count", 0), "| **edges:**", debug_info.get("graph_edge_count", 0))
                st.write("**Nodes by type:**", debug_info.get("graph_nodes_by_type", {}))
                p = debug_info.get("paths") or {}
                st.write("**Paths:** cwd:", p.get("cwd", "—"))
                st.write("- uploads_dir:", p.get("uploads_dir", "—"), "exists:", p.get("uploads_exists"))
                st.write("- facts_path:", p.get("facts_path", "—"), "exists:", p.get("facts_exists"), "size:", p.get("facts_size", 0))
                st.write("- graph_path:", p.get("graph_path", "—"), "exists:", p.get("graph_exists"), "size:", p.get("graph_size", 0))

    # Strategy Advisor chat – always visible so users see the space
    st.subheader("Strategy Advisor chat")
    st.caption("Ask a coaching question. Answers use only this client's traits, drivers, and risks from the graph. Build insights above first (upload PDF + client name) to get advice.")
    # Show chat history above the input
    for msg in st.session_state.get("kg_chat_history") or []:
        if msg.get("role") == "user":
            with st.chat_message("user"):
                st.write(msg.get("content", ""))
        else:
            with st.chat_message("assistant"):
                r = msg.get("content") or {}
                st.markdown("**1. Recommendation**")
                st.write(r.get("recommendation", ""))
                st.markdown("**2. Why**")
                st.write(r.get("why") or "—")
                st.markdown("**3. Signals still missing**")
                for m in r.get("signals_still_missing") or []:
                    st.markdown(f"- {m}")
                if not r.get("signals_still_missing"):
                    st.write("—")
                st.markdown("**4. Suggested next step**")
                st.write(r.get("suggested_next_step", ""))

    advisor_question = st.chat_input("Ask the Strategy Advisor...", key="kg_advisor_chat")
    if advisor_question and (advisor_question := advisor_question.strip()):
        ctx = {"client_name": current_client or "Unknown", "traits": [], "drivers": [], "risks": []}
        if current_client:
            G = bg.load_graph()
            if G.has_node(kg_ontology.client_id(current_client)):
                tdr = bg.get_client_traits_drivers_risks(G, current_client)
                ctx["traits"] = [{"label": t.get("label"), "evidence": t.get("evidence")} for t in (tdr.get("traits") or [])]
                ctx["drivers"] = [{"label": d.get("label"), "evidence": d.get("evidence")} for d in (tdr.get("drivers") or [])]
                ctx["risks"] = [{"label": r.get("label"), "evidence": r.get("evidence")} for r in (tdr.get("risks") or [])]
        result = advisor.advise(ctx, advisor_question)
        st.session_state.setdefault("kg_chat_history", []).append({"role": "user", "content": advisor_question})
        st.session_state["kg_chat_history"].append({"role": "assistant", "content": result})
        st.rerun()

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

        # Section D: Similar Clients
        st.subheader("Similar clients")
        similar = sim.get_similar_clients(traits, drivers, risks, top_n=5)
        if similar:
            for sclient, score, overlap in similar:
                st.markdown(f"**{sclient.get('name', '')}** — {sclient.get('business_type', '')}")
                st.caption(f"Similarity: {score:.2f}. Overlap: {', '.join(overlap[:5])}.")
        else:
            st.caption("No similar clients in seed set. Add entries to data/clients_seed.json.")

        # Section E: Interactive Graph View
        _render_interactive_graph_view(current_client, traits, drivers, risks)
    else:
        st.caption("Upload a PDF and enter a client name, then click Build Insights.")
        # Still show graph section with client selector from graph
        G = _cached_load_graph()
        clients_in_g = viz.get_clients_in_graph(G)
        if clients_in_g:
            st.subheader("Interactive Graph view")
            st.caption("Select a client that has graph data to view the graph.")
            sel = st.selectbox("Client", clients_in_g, key="kg_graph_client_empty")
            if sel:
                _render_interactive_graph_view(sel, [], [], [])


@st.cache_data(ttl=120)
def _cached_load_graph():
    return bg.load_graph()


@st.cache_data(ttl=120)
def _cached_agraph_elements(client_name: str, focus: str, depth: int, show_documents: bool):
    G = bg.load_graph()
    return viz.build_agraph_elements(G, client_name, focus, depth, viz.DEFAULT_NODE_LIMIT, show_documents)


def _render_interactive_graph_view(current_client: str, traits, drivers, risks):
    st.subheader("Interactive Graph view")
    G = _cached_load_graph()
    clients_in_g = viz.get_clients_in_graph(G)
    client_options = [current_client] if current_client and current_client not in clients_in_g else []
    client_options = list(dict.fromkeys([current_client] + clients_in_g)) if current_client else clients_in_g
    if not client_options:
        client_options = clients_in_g or ["(no clients in graph)"]
    sel_client = st.selectbox("Client", client_options, key="kg_graph_client")
    focus = st.selectbox(
        "Focus",
        [viz.FOCUS_ALL, viz.FOCUS_TRAITS, viz.FOCUS_DRIVERS, viz.FOCUS_RISKS, viz.FOCUS_RECOMMENDATIONS, viz.FOCUS_DOCUMENTS],
        key="kg_graph_focus",
    )
    depth = st.slider("Depth", 1, 2, 1, key="kg_graph_depth")
    show_docs = st.checkbox("Show Documents", value=False, key="kg_show_docs")
    nodes_out, edges_out, details_map = _cached_agraph_elements(sel_client, focus, depth, show_docs)

    left, right = st.columns([2, 1])
    with left:
        no_data = not nodes_out or (len(nodes_out) == 1 and nodes_out[0].get("id") == "no_client")
        if no_data:
            st.info("Build insights for this client first. Upload a PDF, enter the client name above, and click **Build Insights**.")
            _fallback_graph_view(traits, drivers, risks)
        else:
            try:
                from streamlit_agraph import agraph, Node, Edge, Config
                agraph_nodes = [Node(id=n["id"], label=n["label"], color=n.get("color", "#757575"), size=25) for n in nodes_out]
                agraph_edges = [Edge(source=e["source"], target=e["target"], label=e.get("label", "")) for e in edges_out]
                config = Config(width=600, height=450, directed=True, physics=True, hierarchical=False)
                agraph(nodes=agraph_nodes, edges=agraph_edges, config=config)
            except Exception:
                _fallback_graph_view(traits, drivers, risks)
    with right:
        st.markdown("**Selected Node Details**")
        node_options = [(n["id"], n["label"]) for n in nodes_out]
        if node_options:
            choice_labels = [f"{lab} ({nid[:20]}...)" if len(nid) > 20 else f"{lab}" for nid, lab in node_options]
            idx = st.selectbox("Select node", range(len(choice_labels)), format_func=lambda i: choice_labels[i], key="kg_node_sel")
            nid = node_options[idx][0]
            det = details_map.get(nid, {})
            st.markdown(f"**Type:** {det.get('type', '—')}")
            st.markdown(f"**Label:** {det.get('label', '—')}")
            st.markdown("**Connections**")
            for e in det.get("edges") or []:
                st.caption(f"{e.get('relation', '')} → {e.get('target', '')}")
            st.markdown("**Evidence**")
            for ev in det.get("evidence") or []:
                st.caption(f"p.{ev.get('page', '?')}: {ev.get('snippet', '')[:100]}...")
            if det.get("why"):
                st.markdown("**Why**")
                st.caption(det.get("why"))
        else:
            st.caption("Build insights for this client first (upload PDF + client name, then Build Insights).")

    st.markdown("**Graph Summary**")
    summary = viz.graph_summary(G, sel_client)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.caption("Counts by type")
        for k, v in (summary.get("counts") or {}).items():
            st.caption(f"{k}: {v}")
    with c2:
        st.caption("Top traits")
        for t in summary.get("top_traits") or []:
            st.caption(f"- {t[:50]}")
    with c3:
        st.caption("Top drivers")
        for d in summary.get("top_drivers") or []:
            st.caption(f"- {d[:50]}")


def _fallback_graph_view(traits, drivers, risks):
    if traits or drivers or risks:
        st.markdown("**Key traits**")
        for t in (traits or [])[:10]:
            st.markdown(f"- {t.get('label', '')}")
        st.markdown("**Key drivers**")
        for d in (drivers or [])[:10]:
            st.markdown(f"- {d.get('label', '')}")
        st.markdown("**Key risks**")
        for r in (risks or [])[:10]:
            st.markdown(f"- {r.get('label', '')}")
