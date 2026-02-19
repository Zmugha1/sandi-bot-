"""
Career & Business Fit: upload PDF, build insights, show Top 5 careers, Top 5 businesses, call plan, email draft.
Simple UI, no icons. Deterministic by default. Graph internal; optional "Show Graph" at bottom.
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
from kg import visualize as viz
from kg import context_pack as cp
from kg import signals as sig
from kg import fit_scoring as fit
from kg import templates as tpl


def _client_slug(name: str) -> str:
    return "".join(c if c.isalnum() or c in " -_" else "" for c in (name or "").strip()).replace(" ", "_").replace("-", "_")[:64] or "client"


def _build_debug_info(client_name: str, doc_id: str, extraction: Optional[dict], G, pdf_bytes: Optional[bytes]) -> dict:
    facts = extraction.get("facts") or [] if extraction else []
    by_type = (extraction.get("facts_count_by_type") or {}) if extraction else {}
    if not by_type and facts:
        for f in facts:
            if f is None or not isinstance(f, dict):
                continue
            t = f.get("type") or "unknown"
            by_type[t] = by_type.get(t, 0) + 1
    node_counts = {}
    for nid in G.nodes():
        attrs = G.nodes[nid] if hasattr(G, "nodes") else {}
        nt = str(attrs.get("node_type") or "unknown") if attrs is not None else "unknown"
        node_counts[nt] = node_counts.get(nt, 0) + 1
    paths = stg.get_paths_for_debug()
    return {
        "client_name": client_name,
        "doc_id": doc_id,
        "pdf_pages": len(ext.extract_text_by_page(pdf_bytes)) if pdf_bytes else 0,
        "facts_extracted_count": len(facts),
        "facts_by_type": by_type,
        "facts_count_by_type": by_type,
        "graph_node_count": G.number_of_nodes(),
        "graph_edge_count": G.number_of_edges(),
        "graph_nodes_by_type": node_counts,
        "paths": paths,
        "total_chars_extracted": extraction.get("total_chars_extracted") if extraction else None,
        "pages_with_text_count": extraction.get("pages_with_text_count") if extraction else None,
        "extraction_status": extraction.get("extraction_status") if extraction else None,
        "headings_found": extraction.get("headings_found") if extraction else None,
        "bullets_found": extraction.get("bullets_found") if extraction else None,
        "client_node_id": kg_ontology.client_id(client_name),
    }


def render():
    st.title("Career & Business Fit")
    st.caption("Upload a personality report PDF and build insights. You'll see top career fits, business fits, a call plan, and optional email draft. All evidence from the document.")

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
            client_slug = _client_slug(current_client)
            stg.ensure_dirs()
            save_path = stg.save_upload(client_slug, pdf_file.name, pdf_bytes)

            # Already processed: doc_id in client index, or legacy: facts exist for this client+doc_id
            already_processed = stg.client_has_doc_id(current_client, doc_id)
            if not already_processed:
                legacy_facts = stg.load_facts_for_client(current_client, doc_id=doc_id)
                if legacy_facts:
                    already_processed = True
                    stg.register_processed_doc(client_slug, current_client, doc_id, str(save_path), len(legacy_facts), graph_updated=True)
            if already_processed:
                st.info("This report was already processed for this client. No duplicate facts added. Loading from graph.")
                G = bg.load_graph()
                if G.number_of_nodes() == 0 and stg.FACTS_JSONL.exists():
                    G = bg.rebuild_graph_from_facts()
                    bg.save_graph(G)
                    _cached_load_graph.clear()
                    _cached_agraph_elements.clear()
                    G = bg.load_graph()
                facts_from_file = stg.load_facts_for_client(current_client, doc_id=doc_id)
                if facts_from_file:
                    extraction = {
                        "client_name": current_client,
                        "doc_id": doc_id,
                        "facts": [{"type": f.get("type"), "label": f.get("label"), "evidence": f.get("evidence")} for f in facts_from_file],
                    }
                else:
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
                if extraction.get("extraction_status") == "text_extraction_failed":
                    st.error(extraction.get("extraction_message") or "Text extraction failed. Please upload a text-based PDF.")
                    debug_info = _build_debug_info(current_client, doc_id, extraction, bg.load_graph(), pdf_bytes)
                else:
                    num_facts = len(extraction.get("facts") or [])
                    for fact in extraction.get("facts") or []:
                        row = {
                            "client_slug": client_slug,
                            "client_display_name": current_client,
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
                    stg.register_processed_doc(client_slug, current_client, doc_id, str(save_path), num_facts, graph_updated=True)
                    _cached_load_graph.clear()
                    _cached_agraph_elements.clear()
                    debug_info = _build_debug_info(current_client, doc_id, extraction, G, pdf_bytes)
                    st.success(f"Processed {num_facts} insights. Saved to {save_path.name}.")
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
            with st.expander("Debug Panel", expanded=False):
                st.write("**Client:**", debug_info.get("client_name", "—"))
                st.write("**client_node_id (for visualization):**", debug_info.get("client_node_id", "—"))
                st.write("**doc_id:**", debug_info.get("doc_id", "—"))
                st.write("**PDF pages:**", debug_info.get("pdf_pages", "—"))
                st.write("**total_chars_extracted:**", debug_info.get("total_chars_extracted", "—"))
                st.write("**pages_with_text_count:**", debug_info.get("pages_with_text_count", "—"))
                st.write("**extraction_status:**", debug_info.get("extraction_status", "—"))
                st.write("**headings_found:**", debug_info.get("headings_found", "—"))
                st.write("**bullets_found:**", debug_info.get("bullets_found", "—"))
                st.write("**Facts extracted:**", debug_info.get("facts_extracted_count", 0), "| **facts_count_by_type:**", debug_info.get("facts_count_by_type", debug_info.get("facts_by_type", {})))
                st.write("**Graph nodes:**", debug_info.get("graph_node_count", 0), "| **edges:**", debug_info.get("graph_edge_count", 0))
                st.write("**Nodes by type:**", debug_info.get("graph_nodes_by_type", {}))
                p = debug_info.get("paths") or {}
                st.write("**Paths:** cwd:", p.get("cwd", "—"))
                st.write("- uploads_dir:", p.get("uploads_dir", "—"), "exists:", p.get("uploads_exists"))
                st.write("- index_dir:", p.get("index_dir", "—"), "exists:", p.get("index_exists"))
                st.write("- facts_path:", p.get("facts_path", "—"), "exists:", p.get("facts_exists"), "size:", p.get("facts_size", 0))
                st.write("- graph_path:", p.get("graph_path", "—"), "exists:", p.get("graph_exists"), "size:", p.get("graph_size", 0))

    # If we have a client (from form or session), load their insights from graph or facts
    if not extraction and current_client:
        G = bg.load_graph()
        if G.number_of_nodes() == 0 and stg.FACTS_JSONL.exists():
            G = bg.rebuild_graph_from_facts()
            bg.save_graph(G)
            _cached_load_graph.clear()
            _cached_agraph_elements.clear()
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
        else:
            facts_for_client = stg.load_facts_for_client(current_client)
            if facts_for_client:
                extraction = {
                    "client_name": current_client,
                    "doc_id": facts_for_client[0].get("doc_id", "") if facts_for_client else "",
                    "facts": [{"type": f.get("type"), "label": f.get("label"), "evidence": f.get("evidence")} for f in facts_for_client],
                }

    if extraction:
        facts = extraction.get("facts") or []
        signals = sig.normalize_facts_to_signals(facts)
        career_fit = fit.get_career_fit(signals, top_n=5)
        business_fit = fit.get_business_fit(signals, top_n=5)

        # Career Fit Top 5
        st.subheader("Career Fit: Top 5")
        if career_fit:
            for i, c in enumerate(career_fit, 1):
                with st.container():
                    st.markdown(f"**{i}. {c.get('name', '')}** — {c.get('description', '')}")
                    st.caption(f"Why: {c.get('rationale', '')}")
                    for ev in c.get("evidence_used") or []:
                        st.caption(f"Evidence (p.{ev.get('page', '?')}): {(ev.get('snippet') or '')[:150]}...")
                    if c.get("watch_outs"):
                        st.caption("Watch-outs: " + "; ".join(c["watch_outs"]))
                    if c.get("recommended_actions"):
                        for a in c["recommended_actions"][:2]:
                            st.caption(f"- {a}")
                    st.markdown("---")
        else:
            st.caption("Not enough signals. Add more insights from the report and rebuild.")

        # Business Fit Top 5
        st.subheader("Business Fit: Top 5")
        if business_fit:
            for i, b in enumerate(business_fit, 1):
                with st.container():
                    st.markdown(f"**{i}. {b.get('name', '')}** — {b.get('description', '')}")
                    st.caption(f"Why: {b.get('rationale', '')}")
                    for ev in b.get("evidence_used") or []:
                        st.caption(f"Evidence (p.{ev.get('page', '?')}): {(ev.get('snippet') or '')[:150]}...")
                    if b.get("watch_outs"):
                        st.caption("Watch-outs: " + "; ".join(b["watch_outs"]))
                    if b.get("recommended_actions"):
                        for a in b["recommended_actions"][:2]:
                            st.caption(f"- {a}")
                    st.markdown("---")
        else:
            st.caption("Not enough signals. Add more insights from the report and rebuild.")

        # Call Prep (one-page plan)
        st.subheader("Call Prep")
        call_plan = tpl.render_call_plan(signals)
        st.markdown(call_plan)

        # Quick actions: 3 buttons
        st.subheader("Quick actions")
        col1, col2, col3 = st.columns(3)
        with col1:
            plan_clicked = st.button("Plan My Next Call", key="kg_plan_call")
        with col2:
            summary_clicked = st.button("Summarize This Client", key="kg_summary")
        with col3:
            email_clicked = st.button("Draft Follow-up Email", key="kg_email")
        if plan_clicked:
            st.session_state["kg_show_plan"] = True
            st.session_state["kg_show_summary"] = False
            st.session_state["kg_show_email"] = False
        if summary_clicked:
            st.session_state["kg_show_summary"] = True
            st.session_state["kg_show_plan"] = False
            st.session_state["kg_show_email"] = False
        if email_clicked:
            st.session_state["kg_show_email"] = True
            st.session_state["kg_show_plan"] = False
            st.session_state["kg_show_summary"] = False

        if st.session_state.get("kg_show_plan"):
            st.markdown("---")
            st.markdown(tpl.render_call_plan(signals))
        if st.session_state.get("kg_show_summary"):
            st.markdown("---")
            st.markdown(tpl.render_client_summary(signals))
        if st.session_state.get("kg_show_email"):
            st.markdown("---")
            outcome_optional = st.text_input("Call outcome (optional)", value="", key="kg_email_outcome", placeholder="e.g. Agreed next steps")
            use_slm = st.checkbox("Use local SLM to polish email", value=False, key="kg_email_slm")
            if use_slm:
                _render_email_with_slm(current_client, signals, outcome_optional)
            else:
                draft = tpl.render_followup_email_template(signals, outcome_optional, current_client or "there")
                st.text_area("Email draft", value=draft, height=220, key="kg_email_draft")

        # Optional: Show Graph (toggle at bottom)
        show_graph = st.checkbox("Show Graph (advanced)", value=False, key="kg_show_graph")
        if show_graph:
            traits = [f for f in facts if f.get("type") == "trait"]
            drivers = [f for f in facts if f.get("type") == "driver"]
            risks = [f for f in facts if f.get("type") in ("risk", "communication_dont")]
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


def _render_email_with_slm(current_client: str, signals: dict, outcome_text: str):
    """Optional: use local SLM to polish follow-up email. Falls back to template if SLM off or fails."""
    model_path_default = str(REPO_ROOT / "models" / "slm" / "model.gguf")
    model_path = st.text_input("Model path (GGUF)", value=model_path_default, key="kg_slm_path")
    if not Path(model_path).exists():
        st.caption("Model file not found. Using template below.")
        st.markdown(tpl.render_followup_email_template(signals, outcome_text, current_client or "there"))
        return
    G = _cached_load_graph()
    pack = _cached_context_pack(current_client, f"{G.number_of_nodes()}_{G.number_of_edges()}")
    if cp.count_facts_in_pack(pack) < 3:
        st.caption("Not enough evidence in graph. Using template.")
        st.markdown(tpl.render_followup_email_template(signals, outcome_text, current_client or "there"))
        return
    try:
        from slm.prompts import system_prompt_email, user_prompt_email
        system_prompt = system_prompt_email()
        user_prompt = user_prompt_email(pack, call_outcome=outcome_text)
        llm = _cached_llm(model_path)
        llm.config.max_tokens = 250
        out = llm.generate(system_prompt, user_prompt, max_tokens=250)
        disclaimer = "Draft generated from stored client insights; review before sending."
        st.text_area("Email draft", value=(out + "\n\n" + disclaimer) if out else disclaimer, height=220, key="kg_slm_email_out")
    except Exception as e:
        st.caption(f"SLM failed: {e}. Using template.")
        st.markdown(tpl.render_followup_email_template(signals, outcome_text, current_client or "there"))


@st.cache_data(ttl=120)
def _cached_load_graph():
    return bg.load_graph()


@st.cache_data(ttl=300)
def _cached_context_pack(client_name: str, graph_version: str):
    """Context pack keyed by client and graph state."""
    G = bg.load_graph()
    return cp.build_context_pack(G, client_name)


@st.cache_resource
def _cached_llm(model_path: str, n_ctx: int = 4096, n_threads: Optional[int] = None, seed: int = 42):
    """Load GGUF model once per path."""
    from slm.local_llm import LocalLLM, LocalLLMConfig
    import os
    n_threads = n_threads or min(8, (os.cpu_count() or 4))
    cfg = LocalLLMConfig(model_path=model_path, n_ctx=n_ctx, n_threads=n_threads, seed=seed, max_tokens=350)
    return LocalLLM(cfg)


def _render_strategy_tools(current_client: str, G):
    st.subheader("Strategy Tools")
    st.caption("Draft follow-up emails, strategy summaries, or call agendas using only stored client insights. Fully local; no cloud or external server.")
    model_path_default = str(REPO_ROOT / "models" / "slm" / "model.gguf")
    model_path = st.text_input("Model path (GGUF)", value=model_path_default, key="slm_model_path")
    enable_slm = st.checkbox("Enable Local SLM", value=False, key="slm_enable")
    tool_type = st.selectbox(
        "Tool Type",
        ["Email Follow-Up", "Strategy Summary", "Call Agenda"],
        key="slm_tool_type",
    )
    call_duration = 20
    call_outcome = ""
    if tool_type == "Call Agenda":
        call_duration = st.number_input("Call duration (minutes)", min_value=5, max_value=60, value=20, key="slm_duration")
    if tool_type == "Email Follow-Up":
        call_outcome = st.text_input("Call outcome (optional)", value="", key="slm_call_outcome", placeholder="e.g. Agreed next steps")
    gen_clicked = st.button("Generate", type="primary", key="slm_generate")

    if not enable_slm:
        st.info("Local SLM disabled. Turn it on to generate drafts. Recommendations remain deterministic.")
        return

    if not current_client:
        st.caption("Enter a client name and build insights first.")
        return

    graph_version = f"{G.number_of_nodes()}_{G.number_of_edges()}"
    pack = _cached_context_pack(current_client, graph_version)
    fact_count = cp.count_facts_in_pack(pack)

    if gen_clicked:
        if fact_count < 3:
            st.warning("Not enough evidence in graph.")
            return
        if not model_path or not Path(model_path).exists():
            st.error("Model file not found. Place a GGUF model at the path above (see models/slm/README.txt).")
            return
        from slm.prompts import get_prompt_builders
        system_fn, user_fn, max_tokens = get_prompt_builders(tool_type)
        system_prompt = system_fn()
        user_prompt = user_fn(pack, duration_min=call_duration, call_outcome=call_outcome or "")
        with st.spinner("Generating..."):
            try:
                llm = _cached_llm(model_path)
                llm.config.max_tokens = max_tokens
                out = llm.generate(system_prompt, user_prompt, max_tokens=max_tokens)
            except Exception as e:
                st.error(f"Generation failed: {e}")
                return
        disclaimer = "Draft generated from stored client insights; review before sending."
        st.session_state["slm_last_output"] = (out + "\n\n" + disclaimer) if out else disclaimer
        st.session_state["slm_last_pack"] = pack

    if st.session_state.get("slm_last_output"):
        st.text_area("Output", value=st.session_state["slm_last_output"], height=200, key="slm_output")
        st.markdown("**Facts Used**")
        last_pack = st.session_state.get("slm_last_pack") or pack
        for label, key in [("Traits", "traits"), ("Drivers", "drivers"), ("Risks", "risks"), ("Recommendations", "recommendations")]:
            items = last_pack.get(key) or []
            if items:
                st.caption(label)
                for it in items:
                    lab = it.get("label") or it.get("action") or ""
                    evs = it.get("evidence") or []
                    snips = [str(e.get("snippet", ""))[:120] for e in evs if e]
                    st.caption(f"- {lab}" + (f" ({'; '.join(snips)})" if snips else ""))


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
