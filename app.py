"""
Banking Query Copilot Local — Streamlit UI
Run with: streamlit run app.py
"""

import asyncio
import csv
import io
import json
import os
import sys
import time

import streamlit as st

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(__file__))

from agents.coordinator_agent import process_prompt
from core.foundry_client import get_model_info
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_GLOSSARY_PATH = Path(__file__).parent / "data" / "glossary.json"


@st.cache_data
def load_glossary() -> list[dict]:
    with open(_GLOSSARY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _to_csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Demo scenarios — one per domain for the landing cards, full list available
# ---------------------------------------------------------------------------
DEMO_CARDS = [
    {
        "domain": "Finance",
        "icon": "💰",
        "title": "Net Interest Margin",
        "prompt": "Calculate Net Interest Margin by product for UK in Q1 2025",
        "description": "Compute NII & NIM with region and product grouping",
    },
    {
        "domain": "Risk",
        "icon": "⚠️",
        "title": "Expected Credit Loss",
        "prompt": "Show loans that migrated from Stage 1 to Stage 2 in the last 30 days and compute expected credit loss",
        "description": "IFRS 9 stage migration with PD × LGD × EAD calculation",
    },
    {
        "domain": "Treasury",
        "icon": "🏛️",
        "title": "NSFR Compliance",
        "prompt": "Show monthly NSFR trend and flag months below 100%",
        "description": "Basel III liquidity ratio monitoring with breach detection",
    },
    {
        "domain": "AML",
        "icon": "🔍",
        "title": "Structuring Detection",
        "prompt": "Find customers with repeated cash deposits just below reporting thresholds within 7 days",
        "description": "Transaction pattern analysis for potential smurfing",
    },
]

MORE_DEMOS = [
    ("Finance — NII for Mortgages", "What is the net interest income for mortgages in Q1 2025?", "Finance"),
    ("Finance — NII by Region", "Compare Net Interest Income across all regions for January 2025", "Finance"),
    ("Risk — ECL Stage 2 UK", "Calculate ECL for all Stage 2 loans in the UK", "Risk"),
    ("Risk — PD by Product", "Show average PD by product for UK Stage 2 loans", "Risk"),
    ("Treasury — NSFR Check", "Is our NSFR above the regulatory minimum this quarter?", "Treasury"),
    ("Treasury — Stable Funding", "What is our total available stable funding for UK in Q1 2025?", "Treasury"),
    ("AML — Recent Activity", "Flag any potential structuring activity on cash deposits in the last week", "AML"),
    ("AML — SAR Candidates", "Flag transactions that may warrant a SAR filing based on structuring patterns", "AML"),
]


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Banking Query Copilot", page_icon="🏦", layout="wide")

# ---------------------------------------------------------------------------
# Sidebar — status & reference only
# ---------------------------------------------------------------------------
with st.sidebar:
    model_info = get_model_info()
    connected = model_info["connected"]

    if connected:
        st.markdown("### 🟢 Foundry Local — Online")
        st.caption(f"**Alias:** `{model_info['alias']}`")
        if model_info["model_id"] and model_info["model_id"] != model_info["alias"]:
            st.caption(f"**Model:** `{model_info['model_id']}`")
        if model_info["device"]:
            st.caption(f"**Device:** {model_info['device']}")
    else:
        st.markdown("### 🔴 Foundry Local — Offline")
        st.caption("No model available")

    st.divider()
    st.markdown("### More demos")
    more_demo_sel = st.selectbox(
        "Pick a scenario",
        ["—"] + [d[0] for d in MORE_DEMOS],
        key="more_demos",
    )
    if more_demo_sel != "—":
        idx = [d[0] for d in MORE_DEMOS].index(more_demo_sel)
        st.session_state["run_prompt"] = MORE_DEMOS[idx][1]
        st.session_state["run_domain"] = MORE_DEMOS[idx][2]

    st.divider()
    with st.expander("📖 Glossary (32 terms)"):
        glossary = load_glossary()
        for domain in ["Finance", "Risk", "Treasury", "AML"]:
            terms = [g for g in glossary if g["domain"] == domain]
            st.markdown(f"**{domain}**")
            for t in terms:
                st.caption(f"**{t['term']}** — {t['full_name']}")

    st.divider()
    st.markdown(
        "[Foundry Local](https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-local/get-started) · "
        "[Agent Framework](https://github.com/microsoft/agents) · MIT"
    )

# ---------------------------------------------------------------------------
# Main area — header
# ---------------------------------------------------------------------------
st.markdown("## 🏦 Banking Query Copilot")
st.caption("Multi-agent structured-output demo — runs entirely on your machine via Foundry Local")

# ---------------------------------------------------------------------------
# Main area — prompt input (top of page, natural focus)
# ---------------------------------------------------------------------------
col_prompt, col_domain, col_run = st.columns([6, 1, 1])
with col_prompt:
    prompt_val = st.session_state.pop("run_prompt", "")
    user_prompt = st.text_input(
        "Ask a banking analytics question",
        value=prompt_val,
        placeholder="e.g. Calculate Net Interest Margin by product for UK in Q1 2025",
        label_visibility="collapsed",
    )
with col_domain:
    domain_val = st.session_state.pop("run_domain", "Auto")
    domain_choice = st.selectbox("Domain", ["Auto", "Finance", "Risk", "Treasury", "AML"],
                                  index=["Auto", "Finance", "Risk", "Treasury", "AML"].index(domain_val),
                                  label_visibility="collapsed")
with col_run:
    run_btn = st.button("▶  Run", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Resolve what to run
# ---------------------------------------------------------------------------
prompt_to_run = None
domain_to_use = domain_choice

# Check for demo card clicks (via session_state)
for card in DEMO_CARDS:
    key = f"card_{card['domain']}"
    if st.session_state.get(key):
        prompt_to_run = card["prompt"]
        domain_to_use = card["domain"]
        st.session_state[key] = False
        break

if prompt_to_run is None and run_btn and user_prompt.strip():
    prompt_to_run = user_prompt.strip()

# ---------------------------------------------------------------------------
# Results view
# ---------------------------------------------------------------------------
if prompt_to_run:
    st.divider()
    st.markdown(f"**Prompt:** {prompt_to_run}")

    start = time.time()
    with st.spinner("Running 6-agent pipeline…"):
        try:
            response = _run_async(process_prompt(prompt_to_run, domain_to_use))
        except Exception as exc:
            st.error(f"Pipeline error: {exc}")
            st.stop()
    elapsed = time.time() - start
    st.success(f"Done in {elapsed:.2f}s — 6 agents executed")

    # Summary metrics
    summary = response.get("summary", {})
    if summary:
        metric_cols = st.columns(min(len(summary), 4))
        for i, (k, v) in enumerate(summary.items()):
            metric_cols[i % len(metric_cols)].metric(k.replace("_", " ").title(), str(v))

    # Results table
    results = response.get("results", [])
    if results:
        st.dataframe(results, use_container_width=True)
        st.download_button("📥 Download CSV", _to_csv(results), "results.csv", "text/csv")
    else:
        st.info("No result rows returned.")

    # Safety notes — always visible
    for note in response.get("safety_notes", []):
        st.warning(note)

    # Explanation
    explanation = response.get("explanation", "")
    if explanation:
        with st.expander("📝 Explanation", expanded=True):
            st.markdown(explanation)

    # Technical details — collapsed
    with st.expander("📋 Query Plan (JSON)"):
        st.json(response.get("query_plan", {}))

    with st.expander("🔍 Agent Trace"):
        for i, step in enumerate(response.get("agent_trace", []), 1):
            st.text(f"  {i}. {step}")

elif not user_prompt.strip():
    # ------------------------------------------------------------------
    # Landing page — demo cards
    # ------------------------------------------------------------------
    st.divider()

    cols = st.columns(4)
    for col, card in zip(cols, DEMO_CARDS):
        with col:
            st.markdown(f"### {card['icon']} {card['domain']}")
            st.markdown(f"**{card['title']}**")
            st.caption(card["description"])
            st.button(
                f"▶ Try it",
                key=f"card_{card['domain']}",
                use_container_width=True,
            )

    st.divider()
    st.caption(
        "**How it works:** Your prompt → Ontology Agent (classify) → Planner Agent (skeleton) → "
        "Generator Agent (LLM → JSON) → Output Controller (validate + repair) → "
        "Executor (run over data) → Explainer (human summary). "
        "Browse more demos and the glossary in the sidebar."
    )
