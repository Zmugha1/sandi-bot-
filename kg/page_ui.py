"""
Career & Business Fit Report: upload PDF, generate top career and business fits with evidence-backed rationale.
Primary output: Career Fit Top 5, Business Fit Top 5. Supporting Insights and Advanced (graph/debug) collapsed.
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

_MIN_SIGNALS_FOR_FIT = 1


def _client_slug(name: str) -> str:
    return "".join(c if c.isalnum() or c in " -_" else "" for c in (name or "").strip()).replace(" ", "_").replace("-", "_")[:64] or "client"


def _render_fit_card(rank: int, item: dict) -> None:
    """Render one Career or Business Fit card: rank, name, description, Why, Evidence, Watch-outs, Recommended (max 2)."""
    name = item.get("name") or ""
    desc = (item.get("description") or "").strip()
    st.markdown(f"**{rank}. {name}** — {desc}")
    rationale = item.get("rationale") or ""
    if rationale:
        st.caption(f"Why: {rationale}")
    evidence_list = item.get("evidence_used") or []
    if evidence_list:
        st.caption("Evidence:")
        for ev in evidence_list[:2]:
            page = ev.get("page", "?")
            snippet = (ev.get("snippet") or "").strip()
            if snippet:
                st.caption(f'  (p.{page}) "{snippet}"')
    watch_outs = item.get("watch_outs") or []
    if watch_outs:
        st.caption("Watch-outs:")
        for w in watch_outs[:2]:
            st.caption(f"  - {w}")
    actions = item.get("recommended_actions") or []
    for a in actions[:2]:
        if a:
            st.caption(f"- {a}")
    st.markdown("---")


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
    st.caption("Upload a personality report to generate top career and business fits with evidence-backed rationale.")

    # Session state: no auto-load; results only after explicit Generate or Load
    if "kg_has_results" not in st.session_state:
        st.session_state["kg_has_results"] = False
    if "kg_active_client_slug" not in st.session_state:
        st.session_state["kg_active_client_slug"] = None
    if "kg_active_doc_id" not in st.session_state:
        st.session_state["kg_active_doc_id"] = None
    if "kg_last_action" not in st.session_state:
        st.session_state["kg_last_action"] = None
    if "kg_extraction" not in st.session_state:
        st.session_state["kg_extraction"] = None
    if "kg_debug_info" not in st.session_state:
        st.session_state["kg_debug_info"] = {}
    if "kg_result_client_name" not in st.session_state:
        st.session_state["kg_result_client_name"] = None

    # Reset button (always visible when we have results)
    if st.session_state.get("kg_has_results"):
        if st.button("Clear / Reset", key="kg_reset"):
            st.session_state["kg_has_results"] = False
            st.session_state["kg_active_client_slug"] = None
            st.session_state["kg_active_doc_id"] = None
            st.session_state["kg_last_action"] = None
            st.session_state["kg_extraction"] = None
            st.session_state["kg_debug_info"] = {}
            st.session_state["kg_result_client_name"] = None
            st.rerun()

    # Tabs: New Report | Load Existing
    tab_new, tab_load = st.tabs(["New Report", "Load Existing"])

    extraction = None
    current_client = None
    debug_info = {}

    with tab_new:
        st.subheader("New Report")
        pdf_file = st.file_uploader("Personality Report (PDF)", type=["pdf"], key="kg_pdf")
        client_name_new = st.text_input("Client Name", value="", key="kg_client_name", placeholder="Required")
        current_client = (client_name_new or "").strip()
        # Clear results if user changed client name (demo-safe: no stale report)
        if st.session_state.get("kg_has_results") and st.session_state.get("kg_result_client_name"):
            if current_client != st.session_state.get("kg_result_client_name"):
                st.session_state["kg_has_results"] = False
                st.session_state["kg_active_client_slug"] = None
                st.session_state["kg_active_doc_id"] = None
                st.session_state["kg_last_action"] = None
                st.session_state["kg_extraction"] = None
                st.session_state["kg_debug_info"] = {}
                st.session_state["kg_result_client_name"] = None
        business_type = st.selectbox(
            "Business Type (optional)",
            ["", "IT Services", "Healthcare Consulting", "Financial Advisory", "Marketing Agency", "Legal Services", "Other"],
            key="kg_business_type",
        )
        build_clicked = st.button("Generate Fit Report", type="primary", key="kg_build")

        if build_clicked and pdf_file is not None and current_client:
            with st.spinner("Extracting insights..."):
                pdf_bytes = pdf_file.read()
                doc_id = stg.doc_id_from_bytes(pdf_bytes)
                client_slug = _client_slug(current_client)
                stg.ensure_dirs()
                save_path = stg.save_upload(client_slug, pdf_file.name, pdf_bytes)

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
                    st.session_state["kg_has_results"] = True
                    st.session_state["kg_active_client_slug"] = client_slug
                    st.session_state["kg_active_doc_id"] = doc_id
                    st.session_state["kg_last_action"] = "generate"
                    st.session_state["kg_extraction"] = extraction
                    st.session_state["kg_debug_info"] = debug_info
                    st.session_state["kg_result_client_name"] = current_client
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
                        st.session_state["kg_has_results"] = True
                        st.session_state["kg_active_client_slug"] = client_slug
                        st.session_state["kg_active_doc_id"] = doc_id
                        st.session_state["kg_last_action"] = "generate"
                        st.session_state["kg_extraction"] = extraction
                        st.session_state["kg_debug_info"] = debug_info
                        st.session_state["kg_result_client_name"] = current_client
                        st.success("Report generated.")
        elif build_clicked and not current_client:
            st.warning("Please enter a client name.")
        elif build_clicked and pdf_file is None:
            st.warning("Please upload a PDF.")

    with tab_load:
        st.subheader("Load Existing")
        # Only load graph when user clicks Refresh (no load on initial render)
        if "kg_client_list" not in st.session_state:
            st.session_state["kg_client_list"] = []
        if st.button("Refresh client list", key="kg_refresh_clients"):
            G = bg.load_graph()
            if G.number_of_nodes() == 0 and stg.FACTS_JSONL.exists():
                G = bg.rebuild_graph_from_facts()
                bg.save_graph(G)
                _cached_load_graph.clear()
                _cached_agraph_elements.clear()
                G = bg.load_graph()
            st.session_state["kg_client_list"] = viz.get_clients_in_graph(G) or []
            st.rerun()
        client_options = ["— Select —"] + list(st.session_state["kg_client_list"])
        selected_label = st.selectbox("Client", client_options, key="kg_load_select", index=0)
        load_clicked = st.button("Load Existing Client", type="primary", key="kg_load_btn")
        if load_clicked and selected_label and selected_label != "— Select —":
            G = bg.load_graph()
            if G.number_of_nodes() == 0 and stg.FACTS_JSONL.exists():
                G = bg.rebuild_graph_from_facts()
                bg.save_graph(G)
                _cached_load_graph.clear()
                _cached_agraph_elements.clear()
                G = bg.load_graph()
            load_client = selected_label
            if G.has_node(kg_ontology.client_id(load_client)):
                extraction = {"client_name": load_client, "doc_id": "", "facts": []}
                tdr = bg.get_client_traits_drivers_risks(G, load_client)
                for item in tdr.get("traits") or []:
                    extraction["facts"].append({"type": "trait", "label": item.get("label"), "evidence": item.get("evidence")})
                for item in tdr.get("drivers") or []:
                    extraction["facts"].append({"type": "driver", "label": item.get("label"), "evidence": item.get("evidence")})
                for item in tdr.get("risks") or []:
                    extraction["facts"].append({"type": "risk", "label": item.get("label"), "evidence": item.get("evidence")})
            else:
                facts_for_client = stg.load_facts_for_client(load_client)
                if facts_for_client:
                    extraction = {"client_name": load_client, "doc_id": facts_for_client[0].get("doc_id", "") if facts_for_client else "", "facts": [{"type": f.get("type"), "label": f.get("label"), "evidence": f.get("evidence")} for f in facts_for_client]}
                else:
                    extraction = None
            if extraction:
                G = _cached_load_graph()
                debug_info = _build_debug_info(load_client, extraction.get("doc_id") or "", extraction, G, None)
                st.session_state["kg_has_results"] = True
                st.session_state["kg_active_client_slug"] = _client_slug(load_client)
                st.session_state["kg_active_doc_id"] = extraction.get("doc_id") or ""
                st.session_state["kg_last_action"] = "load"
                st.session_state["kg_extraction"] = extraction
                st.session_state["kg_debug_info"] = debug_info
                st.session_state["kg_result_client_name"] = load_client
                st.success(f"Loaded data for {load_client}.")
                st.rerun()
            else:
                st.warning("No data found for this client.")

    # Use stored extraction only when user explicitly generated or loaded
    if st.session_state.get("kg_has_results") and st.session_state.get("kg_extraction"):
        extraction = st.session_state["kg_extraction"]
        debug_info = st.session_state.get("kg_debug_info") or {}
        current_client = extraction.get("client_name") or ""

    if st.session_state.get("kg_has_results") and extraction:
        if not debug_info and current_client:
            G = _cached_load_graph()
            debug_info = _build_debug_info(current_client, extraction.get("doc_id") or "", extraction, G, None)
        facts = extraction.get("facts") or []
        signals = sig.normalize_facts_to_signals(facts)
        num_signals = len(signals)
        num_pages = extraction.get("pages_with_text_count") or 0

        # Extraction Quality (short line, no long debug)
        st.caption(f"Extraction Quality: Extracted {num_signals} signals from {num_pages} pages.")

        if num_signals < _MIN_SIGNALS_FOR_FIT:
            st.info(
                "We couldn't extract enough clean signals from this PDF. "
                "Try exporting a text-based PDF or a different report version."
            )
        else:
            career_fit = fit.get_career_fit(signals, top_n=5)
            business_fit = fit.get_business_fit(signals, top_n=5)

            # 1) Career Fit: Top 5
            st.subheader("Career Fit: Top 5")
            if career_fit:
                for i, c in enumerate(career_fit, 1):
                    _render_fit_card(i, c)
            else:
                st.caption("No career fits matched. Add more insights from the report and regenerate.")

            # 2) Business Fit: Top 5
            st.subheader("Business Fit: Top 5")
            if business_fit:
                for i, b in enumerate(business_fit, 1):
                    _render_fit_card(i, b)
            else:
                st.caption("No business fits matched. Add more insights from the report and regenerate.")

        # 3) Supporting Insights (collapsed by default)
        with st.expander("Supporting Insights", expanded=False):
            if num_signals >= _MIN_SIGNALS_FOR_FIT and signals:
                for tag, data in sorted(signals.items(), key=lambda x: -float(x[1].get("score", 0))):
                    score = data.get("score", 0)
                    st.caption(f"**{tag}** (score {score})")

        # 4) Advanced: graph + debug + Drafting Tools (collapsed by default)
        with st.expander("Advanced", expanded=False):
            if debug_info:
                st.markdown("**Debug Panel**")
                st.write("Client:", debug_info.get("client_name", "—"), "| doc_id:", debug_info.get("doc_id", "—"))
                st.write("Facts:", debug_info.get("facts_extracted_count", 0), "| by type:", debug_info.get("facts_count_by_type", {}))
                st.write("Graph nodes:", debug_info.get("graph_node_count", 0), "| edges:", debug_info.get("graph_edge_count", 0))
            show_graph = st.checkbox("Show Graph", value=False, key="kg_show_graph")
            if show_graph:
                traits = [f for f in facts if f.get("type") == "trait"]
                drivers = [f for f in facts if f.get("type") == "driver"]
                risks = [f for f in facts if f.get("type") in ("risk", "communication_dont", "trait_dont")]
                _render_interactive_graph_view(current_client, traits, drivers, risks)
            st.markdown("**Drafting Tools**")
            drafting = st.radio(
                "Choose one",
                ["Draft follow-up email", "Call agenda", "Strategy summary"],
                key="kg_drafting_choice",
                label_visibility="collapsed",
            )
            if drafting == "Draft follow-up email":
                outcome_optional = st.text_input("Call outcome (optional)", value="", key="kg_email_outcome", placeholder="e.g. Agreed next steps")
                use_slm = st.checkbox("Use local SLM to polish", value=False, key="kg_email_slm")
                if num_signals >= _MIN_SIGNALS_FOR_FIT:
                    if use_slm:
                        _render_email_with_slm(current_client, signals, outcome_optional)
                    else:
                        draft = tpl.render_followup_email_template(signals, outcome_optional, current_client or "there")
                        st.text_area("Email draft", value=draft, height=180, key="kg_email_draft")
            elif drafting == "Call agenda":
                if num_signals >= _MIN_SIGNALS_FOR_FIT:
                    st.markdown(tpl.render_call_plan(signals))
            elif drafting == "Strategy summary":
                if num_signals >= _MIN_SIGNALS_FOR_FIT:
                    st.markdown(tpl.render_client_summary(signals))
    else:
        st.caption("Upload a PDF and enter a client name, then click **Generate Fit Report**, or use **Load Existing** to open a prior client.")


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
