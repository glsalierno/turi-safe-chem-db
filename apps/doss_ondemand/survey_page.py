"""
Streamlit page component for Process Factors & Life Cycle Factors survey.

This page provides a user-friendly form for assessing the non-auto-scored
TURI P2OASys categories. Results are saved per CAS and displayed alongside
the automatic (Auto6) scores.

CRITICAL: Blank stays blank — default is "Don't know / leave blank", 
never defaults to 2, never auto-fills.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st

from packages.p2oasys_core.survey import (
    BAND_SCORES,
    Category,
    SurveyAnswers,
    delete_survey,
    get_all_options,
    get_subcategories,
    list_saved_surveys,
    load_survey,
    save_survey,
)
from packages.p2oasys_core.lookup import normalize_cas, format_cas_display


# ─────────────────────────────────────────────────────────────────────────────
# Survey Form Component
# ─────────────────────────────────────────────────────────────────────────────

def _option_label(opt: Dict[str, Any]) -> str:
    """Format option label for selectbox."""
    return f"Score {opt['score']}: {opt['description']}"


def _blank_option() -> str:
    """Return the blank/don't know option label."""
    return "Don't know / leave blank"


def render_subcategory_question(
    category: Category,
    subcategory: str,
    current_score: Optional[int],
    current_note: str,
    key_prefix: str,
) -> tuple[Optional[int], str]:
    """
    Render a single subcategory question with radio buttons.
    
    Returns (selected_score, note) where score is None for blank.
    """
    options = get_all_options(category, subcategory)
    
    # Build option list: blank first, then scores
    option_labels = [_blank_option()] + [_option_label(opt) for opt in options]
    
    # Determine current selection index
    if current_score is None:
        current_index = 0  # Blank
    else:
        try:
            score_idx = next(i for i, opt in enumerate(options) if opt["score"] == current_score)
            current_index = score_idx + 1  # +1 because blank is at index 0
        except StopIteration:
            current_index = 0
    
    # Render
    st.markdown(f"**{subcategory}**")
    selected = st.radio(
        label=subcategory,
        options=option_labels,
        index=current_index,
        key=f"{key_prefix}_{category.value}_{subcategory}",
        label_visibility="collapsed",
    )
    
    # Optional note
    note = st.text_input(
        "Note (optional)",
        value=current_note,
        key=f"{key_prefix}_{category.value}_{subcategory}_note",
        placeholder="Add context or reasoning...",
    )
    
    # Parse selection back to score
    if selected == _blank_option():
        return None, note
    
    for opt in options:
        if _option_label(opt) == selected:
            return opt["score"], note
    
    return None, note


def render_category_section(
    category: Category,
    answers: SurveyAnswers,
    key_prefix: str,
) -> Dict[str, tuple[Optional[int], str]]:
    """
    Render all subcategory questions for a category.
    
    Returns dict of subcategory -> (score, note).
    """
    st.markdown(f"### {category.value}")
    
    results = {}
    subcategories = get_subcategories(category)
    
    for subcategory in subcategories:
        current_answer = answers.get_answer(category, subcategory)
        current_score = current_answer.score if current_answer else None
        current_note = current_answer.note if current_answer else ""
        
        with st.container():
            score, note = render_subcategory_question(
                category, subcategory, current_score, current_note, key_prefix
            )
            results[subcategory] = (score, note)
        
        st.markdown("---")
    
    return results


def render_survey_summary(answers: SurveyAnswers) -> None:
    """Render survey results summary."""
    summary = answers.summary()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Process Factors")
        pf = summary["process_factors"]
        st.metric(
            "Answered",
            f"{pf['answered']}/{pf['total']}",
            help="Number of subcategories with user-provided scores",
        )
        if pf["max"] is not None:
            st.metric("Max Score", pf["max"])
            st.metric("Mean Score", f"{pf['mean']:.1f}")
        else:
            st.info("No scores provided yet")
    
    with col2:
        st.markdown("#### Life Cycle Factors")
        lcf = summary["life_cycle_factors"]
        st.metric(
            "Answered",
            f"{lcf['answered']}/{lcf['total']}",
            help="Number of subcategories with user-provided scores",
        )
        if lcf["max"] is not None:
            st.metric("Max Score", lcf["max"])
            st.metric("Mean Score", f"{lcf['mean']:.1f}")
        else:
            st.info("No scores provided yet")


def render_combined_results(
    auto6_overall: Optional[float],
    auto6_source: str,
    answers: SurveyAnswers,
) -> None:
    """
    Render combined view of Auto6 scores and survey results.
    
    CRITICAL: Overall auto score is MAX of Auto6 only.
    Process/Life Cycle are shown separately, never mixed into auto overall.
    """
    st.markdown("### Combined Hazard Assessment")
    
    summary = answers.summary()
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**Auto6 (Science Categories)**")
        if auto6_overall is not None:
            st.metric("Overall", f"{auto6_overall:.0f}", help="Max of Acute, Chronic, Ecological, Fate, Atmospheric, Physical")
            st.caption(f"Source: {auto6_source}")
        else:
            st.info("No Auto6 score available")
    
    with col2:
        st.markdown("**Process Factors (User)**")
        pf = summary["process_factors"]
        if pf["max"] is not None:
            st.metric("Max", pf["max"])
            st.caption(f"{pf['answered']}/{pf['total']} answered")
        else:
            st.info("Not assessed")
    
    with col3:
        st.markdown("**Life Cycle Factors (User)**")
        lcf = summary["life_cycle_factors"]
        if lcf["max"] is not None:
            st.metric("Max", lcf["max"])
            st.caption(f"{lcf['answered']}/{lcf['total']} answered")
        else:
            st.info("Not assessed")
    
    # Note about separation
    st.info(
        "📋 **Note:** Process Factors and Life Cycle Factors are user-assessed and "
        "shown separately from the automated Auto6 overall score. The Auto6 overall "
        "remains the max of the six science categories only."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main Survey Page
# ─────────────────────────────────────────────────────────────────────────────

def render_survey_page(
    cas: str,
    chemical_name: str = "",
    auto6_overall: Optional[float] = None,
    auto6_source: str = "-",
) -> Optional[SurveyAnswers]:
    """
    Render the complete survey page for a CAS.
    
    Args:
        cas: CAS number
        chemical_name: Optional chemical name for display
        auto6_overall: Optional Auto6 overall score for combined display
        auto6_source: Source of Auto6 score
    
    Returns:
        SurveyAnswers if saved, None otherwise
    """
    cas_display = format_cas_display(cas)
    
    st.markdown(f"## P2OASys Survey: {cas_display}")
    if chemical_name:
        st.markdown(f"**Chemical:** {chemical_name}")
    
    st.markdown(
        "Assess Process Factors and Life Cycle Factors for this chemical. "
        "These categories require human expert judgment and cannot be auto-scored."
    )
    
    st.warning(
        "⚠️ **Default is 'Don't know / leave blank'.** Only select a score if you have "
        "sufficient information to make an assessment. Blank answers stay blank."
    )
    
    # Load existing answers
    answers = load_survey(cas)
    if answers is None:
        answers = SurveyAnswers(cas=cas, chemical_name=chemical_name)
    elif chemical_name and not answers.chemical_name:
        answers.chemical_name = chemical_name
    
    # Key prefix for widget state
    key_prefix = f"survey_{normalize_cas(cas)}"
    
    # Survey tabs
    tab_pf, tab_lcf, tab_summary = st.tabs([
        "Process Factors",
        "Life Cycle Factors",
        "Summary & Results",
    ])
    
    with tab_pf:
        pf_results = render_category_section(Category.PROCESS_FACTORS, answers, key_prefix)
    
    with tab_lcf:
        lcf_results = render_category_section(Category.LIFE_CYCLE_FACTORS, answers, key_prefix)
    
    with tab_summary:
        render_survey_summary(answers)
        
        if auto6_overall is not None or answers.count_answered() > 0:
            st.markdown("---")
            render_combined_results(auto6_overall, auto6_source, answers)
    
    # Save button
    st.markdown("---")
    col_save, col_reset, col_delete = st.columns([2, 1, 1])
    
    with col_save:
        if st.button("💾 Save Survey Answers", type="primary", use_container_width=True):
            # Update answers from form state
            for subcategory, (score, note) in pf_results.items():
                answers.set_answer(Category.PROCESS_FACTORS, subcategory, score, note)
            
            for subcategory, (score, note) in lcf_results.items():
                answers.set_answer(Category.LIFE_CYCLE_FACTORS, subcategory, score, note)
            
            # Save
            path = save_survey(answers)
            st.success(f"Survey saved to {path}")
            return answers
    
    with col_reset:
        if st.button("🔄 Reset Form", use_container_width=True):
            # Clear session state for this survey
            for key in list(st.session_state.keys()):
                if key.startswith(key_prefix):
                    del st.session_state[key]
            st.rerun()
    
    with col_delete:
        if st.button("🗑️ Delete Saved", use_container_width=True):
            if delete_survey(cas):
                st.success("Saved survey deleted")
                for key in list(st.session_state.keys()):
                    if key.startswith(key_prefix):
                        del st.session_state[key]
                st.rerun()
            else:
                st.info("No saved survey to delete")
    
    return None


def render_survey_list_sidebar() -> Optional[str]:
    """
    Render sidebar with list of saved surveys.
    Returns selected CAS if user picks one.
    """
    st.sidebar.markdown("### Saved Surveys")
    
    surveys = list_saved_surveys()
    
    if not surveys:
        st.sidebar.info("No saved surveys yet")
        return None
    
    st.sidebar.caption(f"{len(surveys)} saved survey(s)")
    
    for s in surveys:
        progress = s["answered"] / s["total"] if s["total"] > 0 else 0
        label = f"{s['cas']}"
        if s["chemical_name"]:
            label += f" ({s['chemical_name'][:20]})"
        
        with st.sidebar.container():
            st.markdown(f"**{label}**")
            st.progress(progress, text=f"{s['answered']}/{s['total']} answered")
            if st.button(f"Load {s['cas']}", key=f"load_survey_{s['cas']}"):
                return s["cas"]
    
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Standalone page entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """Standalone survey page entry point."""
    st.set_page_config(
        page_title="TURI Safe Chem DB - Survey",
        page_icon="📋",
        layout="wide",
    )
    
    st.title("📋 P2OASys Survey")
    st.markdown(
        "Assess Process Factors and Life Cycle Factors for chemicals. "
        "These are the non-auto-scored TURI matrix categories that require human expert input."
    )
    
    # Sidebar: saved surveys
    selected_from_sidebar = render_survey_list_sidebar()
    
    # CAS input
    st.sidebar.markdown("---")
    st.sidebar.markdown("### New Survey")
    
    cas_input = st.sidebar.text_input(
        "CAS Number",
        value=selected_from_sidebar or "",
        placeholder="e.g., 67-64-1",
        key="survey_cas_input",
    )
    
    chemical_name = st.sidebar.text_input(
        "Chemical Name (optional)",
        placeholder="e.g., Acetone",
        key="survey_chem_name",
    )
    
    if cas_input:
        render_survey_page(cas_input, chemical_name=chemical_name)
    else:
        st.info("Enter a CAS number in the sidebar to start a survey.")
        
        # Show recent surveys
        st.markdown("### Recent Surveys")
        surveys = list_saved_surveys()
        if surveys:
            for s in surveys[:5]:
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    name = s["chemical_name"] or "Unknown"
                    st.markdown(f"**{s['cas']}** — {name}")
                with col2:
                    st.caption(f"{s['answered']}/{s['total']} answered")
                with col3:
                    st.caption(f"Updated: {s['updated_at'][:10]}")
        else:
            st.caption("No surveys saved yet. Enter a CAS number to start.")


if __name__ == "__main__":
    main()
