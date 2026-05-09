"""
ui/components/simple_mode/page_stub.py — Placeholder for Steps 3–6 (Phase 3+).
"""
from __future__ import annotations
import streamlit as st
from stock_engine.ui.components.simple_mode.session import next_step, prev_step, get_session

STEP_TITLES = {
    # Step numbering matches the dispatcher in simple_aa.py: 1 macro, 2 stocks,
    # 3 allocation, 4 perf, 5 risk, 6 SAA, 7 TAA, 8 ARIMAX. Macro / SAA / TAA
    # content was removed 2026-05-07 (AI-generated, unreviewed; macro charts
    # also redundant vs Bloomberg) — only the page entries remain so the
    # navigation flow stays intact while content is rebuilt.
    1: ("Macro Overview",          "US macro regime dashboard — content paused. Source macro from Bloomberg for now."),
    6: ("SAA Decision",            "Strategic Asset Allocation — content paused, awaiting review and rebuild."),
    7: ("TAA Scenario Tilt",       "Tactical Asset Allocation — content paused, awaiting review and rebuild."),
}

def render_stub(step: int) -> None:
    title, desc = STEP_TITLES.get(step, (f"Step {step}", "Coming soon"))
    sess = get_session()

    st.markdown(
        f'<div style="background:#f5eefb;border:1.5px solid #e0d0e8;border-radius:10px;'
        f'padding:28px 32px;text-align:center;margin:40px auto;max-width:520px">'
        f'<div style="font-size:11px;color:#8a0a9e;font-weight:600;letter-spacing:.06em;'
        f'text-transform:uppercase;margin-bottom:8px">STEP {step}</div>'
        f'<div style="font-size:18px;font-weight:600;color:#1a1a1a;margin-bottom:6px">'
        f'{title}</div>'
        f'<div style="font-size:12px;color:#888;line-height:1.6">{desc}</div>'
        f'<div style="margin-top:16px;font-size:11px;color:#bbb">🔧 Implementation in progress</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    c_back, _, c_fwd = st.columns([1, 3, 1])
    with c_back:
        if st.button("← Back", key=f"stub_back_{step}", use_container_width=True):
            prev_step()
    with c_fwd:
        # 8-step flow: 1 macro · 2 stocks · 3 alloc · 4 perf · 5 risk ·
        # 6 SAA · 7 TAA · 8 ARIMAX. Stub serves 6/7 today; "Done" only kicks
        # in on the final step.
        label = "Next →" if step < 8 else "✓ Done"
        if st.button(label, key=f"stub_next_{step}", type="primary",
                     use_container_width=True):
            if step < 8:
                next_step()
            else:
                st.session_state["page"] = "home"
                st.rerun()
