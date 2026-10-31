"""Scenarios and Test Cases pages: generate, review, edit, approve, ask the AI for changes, export to Excel."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ats.generation.excel_export import cases_workbook, combined_workbook, scenarios_workbook
from ats.models import PRIORITIES, SUITABILITY, TEST_TYPES, Scenario, TestCase
from ats.services import Services
from ats.ui.session import notify, require_project, safe, show_notices
from ats.ui.widgets import ModelStream, chip, edit_fields, progress_logger, selected_rows

SCENARIO_SPEC = [
    ("title", "text", None), ("module", "text", None), ("page", "text", None), ("description", "area", None), ("preconditions", "lines", None),
    ("test_type", "select", TEST_TYPES), ("priority", "select", PRIORITIES), ("expected_outcome", "area", None), ("automation_suitability", "select", SUITABILITY),
]  # fmt: skip
CASE_SPEC = [
    ("title", "text", None), ("module", "text", None), ("description", "area", None), ("preconditions", "lines", None), ("test_data", "pairs", None),
    ("steps", "lines", None), ("expected_result", "area", None), ("test_type", "select", TEST_TYPES), ("priority", "select", PRIORITIES),
    ("automation_candidate", "bool", None), ("related_page", "text", None), ("component", "text", None), ("tags", "lines", None),
]  # fmt: skip


def _frame(items: list, columns: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame([{label: getattr(item, attr) for label, attr in columns.items()} for item in items])


def _download(label: str, data: bytes, name: str) -> None:
    st.download_button(label, data, file_name=name, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def _ai_change(label: str, ids: list[str], action) -> None:
    with st.expander("Tell the AI what to change"):
        st.caption("Only the selected rows are changed when rows are selected; otherwise the whole list may be revised. Changed items need approval again.")
        instruction = st.text_area("Instruction", key=f"{label}_instruction", placeholder="Add negative scenarios for the checkout form and remove duplicates.")
        if st.button("Apply change", key=f"{label}_apply"):
            with st.status("The AI is revising...", expanded=True) as status:
                stream = ModelStream()
                summary = safe(lambda: action(instruction, ids or None, stream.callback))
                if summary is not None:
                    status.update(label="Done", state="complete")
                    counts = ", ".join(f"{len(summary[k])} {k}" for k in ("added", "updated", "deleted", "skipped") if summary.get(k))
                    notify(f"Change applied: {counts or 'no differences'}. {summary.get('explanation', '')}".strip())
                    st.rerun()
                status.update(label="Failed", state="error")


def render_scenarios(svc: Services) -> None:
    project = require_project(svc)
    st.header("Test scenarios")
    show_notices()
    scenarios = svc.repo.list_scenarios(project.id)
    with st.expander("Generate scenarios" if scenarios else "Generate scenarios", expanded=not scenarios):
        requirements = st.text_area("Extra requirements or business rules (optional)", key="sc_req", height=90)
        if scenarios:
            st.warning("Generating again replaces the current scenarios; they must be reviewed and approved again.")
        if st.button("Generate scenarios", type="primary"):
            with st.status("Generating scenarios from the discovered application...", expanded=True) as status:
                stream = ModelStream()
                result = safe(lambda: svc.scenarios.generate(project, requirements, on_event=stream.callback))
                status.update(label="Scenarios generated" if result else "Generation failed", state="complete" if result else "error")
            if result:
                notify(f"{len(result)} scenarios generated. Review and approve them.")
                st.rerun()
    if not scenarios:
        return

    approved = sum(s.status == "approved" for s in scenarios)
    a, b, c = st.columns(3)
    a.metric("Scenarios", len(scenarios))
    b.metric("Approved", approved)
    c.metric("Awaiting review", len(scenarios) - approved)
    columns = {"ID": "scenario_id", "Module": "module", "Title": "title", "Type": "test_type", "Priority": "priority", "Automation": "automation_suitability", "Status": "status", "Source": "source"}
    event = st.dataframe(_frame(scenarios, columns), hide_index=True, width="stretch", on_select="rerun", selection_mode="multi-row", key="sc_table")
    ids = selected_rows(event, [s.scenario_id for s in scenarios])
    st.caption("Select rows to act on them. With nothing selected, 'Approve all' approves everything.")

    a, b, c, d = st.columns(4)
    if a.button(f"Approve selected ({len(ids)})", disabled=not ids):
        svc.scenarios.approve(project.id, ids)
        st.rerun()
    if b.button("Approve all"):
        svc.scenarios.approve_all(project.id)
        st.rerun()
    if c.button("Move selected back to draft", disabled=not ids):
        svc.scenarios.unapprove(project.id, ids)
        st.rerun()
    if d.button(f"Delete selected ({len(ids)})", disabled=not ids):
        removed = svc.scenarios.delete(project.id, ids)
        notify(f"Deleted {len(ids)} scenario(s) and {removed} dependent test case(s).")
        st.rerun()

    if len(ids) == 1:
        scenario = next(s for s in scenarios if s.scenario_id == ids[0])
        with st.expander(f"Edit {scenario.scenario_id}", expanded=True):
            values = edit_fields(f"sc_{scenario.scenario_id}", scenario.model_dump(), SCENARIO_SPEC)
            if st.button("Save changes", key=f"sc_save_{scenario.scenario_id}"):
                safe(lambda: svc.scenarios.edit(project.id, Scenario.model_validate({**scenario.model_dump(), **values})))
                notify("Scenario saved. It needs approval again.")
                st.rerun()
    _ai_change("sc", ids, lambda text, scope, cb: svc.scenarios.modify(project, text, scope, on_event=cb))
    with st.expander("Add a scenario manually"):
        with st.form("sc_manual"):
            values = edit_fields("sc_new", {}, SCENARIO_SPEC)
            if st.form_submit_button("Add scenario") and values["title"].strip():
                safe(lambda: svc.scenarios.add_manual(project, **values))
                st.rerun()
    _download("Download scenarios (Excel)", scenarios_workbook(project, scenarios, svc.repo.list_test_cases(project.id)), f"{project.name}_scenarios.xlsx")


def render_test_cases(svc: Services) -> None:
    project = require_project(svc)
    st.header("Test cases")
    show_notices()
    approved_scenarios = svc.repo.list_scenarios(project.id, status="approved")
    cases = svc.repo.list_test_cases(project.id)
    if not approved_scenarios:
        st.info("Approve at least one scenario first. Test cases are generated only from approved scenarios.")
        return
    with st.expander("Generate test cases", expanded=not cases):
        requirements = st.text_area("Extra requirements (optional)", key="tc_req", height=80)
        st.caption(f"{len(approved_scenarios)} approved scenario(s) will be expanded into detailed test cases.")
        if st.button("Generate test cases", type="primary"):
            with st.status("Generating test cases...", expanded=True) as status:
                stream = ModelStream()
                result = safe(lambda: svc.testcases.generate(project, requirements, on_event=stream.callback, progress=progress_logger(status)))
                status.update(label="Test cases generated" if result else "Generation failed", state="complete" if result else "error")
            if result:
                notify(f"{len(result)} test cases generated.")
                st.rerun()
    if not cases:
        return

    approved = sum(c.status == "approved" for c in cases)
    a, b, c, d = st.columns(4)
    a.metric("Test cases", len(cases))
    b.metric("Approved", approved)
    c.metric("Automatable", sum(t.automation_candidate for t in cases))
    d.metric("Scenarios covered", len({t.scenario_id for t in cases}))
    columns = {"ID": "test_case_id", "Scenario": "scenario_id", "Module": "module", "Title": "title", "Type": "test_type", "Priority": "priority", "Automatable": "automation_candidate", "Status": "status"}
    event = st.dataframe(_frame(cases, columns), hide_index=True, width="stretch", on_select="rerun", selection_mode="multi-row", key="tc_table")
    ids = selected_rows(event, [t.test_case_id for t in cases])

    a, b, c, d = st.columns(4)
    if a.button(f"Approve selected ({len(ids)})", disabled=not ids):
        svc.testcases.approve(project.id, ids)
        st.rerun()
    if b.button("Approve all"):
        svc.testcases.approve_all(project.id)
        st.rerun()
    if c.button("Move selected back to draft", disabled=not ids):
        svc.repo.set_test_case_status(project.id, ids, "draft")
        st.rerun()
    if d.button(f"Delete selected ({len(ids)})", disabled=not ids):
        svc.testcases.delete(project.id, ids)
        st.rerun()

    if len(ids) == 1:
        case = next(t for t in cases if t.test_case_id == ids[0])
        with st.expander(f"{case.test_case_id}: {case.title}", expanded=True):
            st.markdown(f"Status {chip(case.status)}")
            values = edit_fields(f"tc_{case.test_case_id}", case.model_dump(), CASE_SPEC)
            if st.button("Save changes", key=f"tc_save_{case.test_case_id}"):
                safe(lambda: svc.testcases.edit(project.id, TestCase.model_validate({**case.model_dump(), **values})))
                notify("Test case saved. It needs approval again.")
                st.rerun()
    _ai_change("tc", ids, lambda text, scope, cb: svc.testcases.modify(project, text, scope, on_event=cb))
    with st.expander("Add a test case manually"):
        scenario_ids = [s.scenario_id for s in svc.repo.list_scenarios(project.id)]
        with st.form("tc_manual"):
            scenario_id = st.selectbox("Scenario", scenario_ids)
            values = edit_fields("tc_new", {}, CASE_SPEC)
            if st.form_submit_button("Add test case") and values["title"].strip():
                safe(lambda: svc.testcases.add_manual(project.id, scenario_id=scenario_id, **values))
                st.rerun()
    a, b = st.columns(2)
    with a:
        _download("Download test cases (Excel)", cases_workbook(project, svc.repo.list_scenarios(project.id), cases), f"{project.name}_test_cases.xlsx")
    with b:
        _download("Download scenarios + test cases + summary (Excel)", combined_workbook(project, svc.repo.list_scenarios(project.id), cases), f"{project.name}_test_design.xlsx")
