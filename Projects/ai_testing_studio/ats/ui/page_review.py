"""Scenarios and Test Cases pages: generate, review, edit, approve, ask the AI for changes, export to Excel."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from ats.api import design as api_design
from ats.generation.excel_export import cases_workbook, combined_workbook, scenarios_workbook
from ats.models import API_TEST_TYPES, PRIORITIES, SUITABILITY, TEST_TYPES, ApiTestSpec, Scenario, TestCase
from ats.services import Services
from ats.ui import jobs_ui, theme
from ats.ui.layers import guarded, layer_label, layer_switch, stop_if_unsupported
from ats.ui.session import go_to, notify, require_project, safe, show_notices
from ats.ui.widgets import chip, edit_fields, selected_rows

SCENARIO_SPEC = [
    ("title", "text", None), ("module", "text", None), ("page", "text", None), ("description", "area", None), ("preconditions", "lines", None),
    ("test_type", "select", TEST_TYPES), ("priority", "select", PRIORITIES), ("expected_outcome", "area", None), ("automation_suitability", "select", SUITABILITY),
]  # fmt: skip
CASE_SPEC = [
    ("title", "text", None), ("module", "text", None), ("description", "area", None), ("preconditions", "lines", None), ("test_data", "pairs", None),
    ("steps", "lines", None), ("expected_result", "area", None), ("test_type", "select", TEST_TYPES), ("priority", "select", PRIORITIES),
    ("automation_candidate", "bool", None), ("related_page", "text", None), ("component", "text", None), ("tags", "lines", None),
]  # fmt: skip


def _spec(spec: list, layer: str) -> list:
    """The editor fields of a layer: API items may also carry the API-only test types."""
    return [(n, k, API_TEST_TYPES if n == "test_type" and layer == "api" else o) for n, k, o in spec]


def _frame(items: list, columns: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame([{label: getattr(item, attr) for label, attr in columns.items()} for item in items])


def _after_approval(svc: Services, project, kind: str, layer: str) -> None:  # noqa: ANN001
    """Once everything in a list is approved the review is finished: continue on the next step's page (the channel stays selected)."""
    label = layer_label(layer) if len(project.layers) > 1 else ""
    prefix = f"{label} " if label else ""
    if kind == "scenarios":
        items, target, text = svc.repo.list_scenarios(project.id, layer=layer), "test-cases", f"{prefix}scenarios approved. Generate the test cases next."
    else:
        items, target, text = svc.repo.list_test_cases(project.id, layer=layer), "automation", f"{prefix}test cases approved. Generate the automation project next."
    if items and all(item.status == "approved" for item in items):
        notify(f"All {len(items)} {text}")
        go_to(target)  # leaves this run; the next page shows the notice
    st.rerun()


def _edited_case(svc: Services, project, case: TestCase, values: dict, requests_json: str, layer: str) -> TestCase | None:  # noqa: ANN001
    """The test case with the editor's values. API requests are parsed and checked against the imported definition; problems are shown, not saved."""
    data = {**case.model_dump(), **values}
    if layer != "api":
        return TestCase.model_validate(data)
    try:
        spec = ApiTestSpec.model_validate(json.loads(requests_json or "{}"))
    except ValueError:
        st.error("The API requests are not valid JSON.")
        return None
    checked, reason = api_design.validate_requests(TestCase.model_validate({**data, "api": spec}), svc.repo.list_api_endpoints(project.id), svc.connections.names(project.id))
    if checked is None:
        st.error(f"The API requests were not saved: {reason}.")
    return checked


def _download(label: str, data: bytes, name: str) -> None:
    st.download_button(label, data, file_name=name, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def _ai_change(svc: Services, project, kind: str, label: str, ids: list[str], action) -> None:  # noqa: ANN001
    with st.expander("Tell the AI what to change"):
        st.caption("Only the selected rows are changed when rows are selected; otherwise the whole list may be revised. Changed items need approval again.")
        instruction = st.text_area("Instruction", key=f"{label}_instruction", placeholder="Add negative scenarios for the checkout form and remove duplicates.")
        if st.button("Apply change", key=f"{label}_apply", disabled=not instruction.strip()):
            def work(ctx):  # noqa: ANN001, ANN202
                summary = action(instruction, ids or None, ctx)
                counts = ", ".join(f"{len(summary[k])} {k}" for k in ("added", "updated", "deleted", "skipped") if summary.get(k))
                return {"counts": counts or "no differences", "explanation": summary.get("explanation", "")}

            jobs_ui.start_job(svc, project, kind, "AI is revising", work, notice="Change applied: {counts}. {explanation}")


def _generation_blocked(svc: Services, project, layer: str) -> str:  # noqa: ANN001
    """Why the layer cannot be generated yet ('' when it can). Web needs a discovery, API needs endpoints."""
    if layer == "api" and not svc.repo.list_api_endpoints(project.id):
        return "Import an API definition (or add endpoints) on the API page first."
    return ""


def render_scenarios(svc: Services) -> None:
    project = require_project(svc)
    theme.page_header("Test scenarios", "Business scenarios generated from the discovered application. Review, edit and approve them.", "STEP 02 // SCENARIOS")
    show_notices()
    layer = layer_switch(project, "scenarios")
    if jobs_ui.running_panel(svc, project, ("scenarios",), "Scenario design in progress"):
        return
    jobs_ui.last_problem(svc, project, ("scenarios",))
    if stop_if_unsupported(layer):
        return
    scenarios = svc.repo.list_scenarios(project.id, layer=layer)
    with st.expander("Generate scenarios" if scenarios else "Generate scenarios", expanded=not scenarios):
        requirements = st.text_area("Extra requirements or business rules (optional)", key="sc_req", height=90)
        if scenarios:
            st.warning("Generating again replaces the current scenarios; they must be reviewed and approved again.")
        blocked = _generation_blocked(svc, project, layer)
        if blocked:
            st.info(blocked)
        if st.button("Generate scenarios", type="primary", disabled=bool(blocked)):
            def work(ctx):  # noqa: ANN001, ANN202
                return {"count": len(svc.scenarios.generate(project, requirements, on_event=ctx.on_event, progress=ctx.reporter, layer=layer))}

            jobs_ui.start_job(
                svc, project, "scenarios", f"Designing {layer_label(layer)} test scenarios" if len(project.layers) > 1 else "Designing test scenarios", guarded(layer, work),
                notice="{count} scenarios generated. Review and approve them.",
            )
    if not scenarios:
        return

    approved = sum(s.status == "approved" for s in scenarios)
    a, b, c = st.columns(3)
    a.metric("Scenarios", len(scenarios))
    b.metric("Approved", approved)
    c.metric("Awaiting review", len(scenarios) - approved)
    columns = {"ID": "scenario_id", "Module": "module", "Title": "title", "Type": "test_type", "Priority": "priority", "Automation": "automation_suitability", "Status": "status", "Source": "source"}
    event = st.dataframe(_frame(scenarios, columns), hide_index=True, width="stretch", on_select="rerun", selection_mode="multi-row", key=f"sc_table_{layer}")
    ids = selected_rows(event, [s.scenario_id for s in scenarios])
    st.caption("Select rows to act on them. With nothing selected, 'Approve all' approves everything.")

    a, b, c, d = st.columns(4)
    if a.button(f"Approve selected ({len(ids)})", disabled=not ids):
        svc.scenarios.approve(project.id, ids)
        _after_approval(svc, project, "scenarios", layer)
    if b.button("Approve all"):
        svc.scenarios.approve_all(project.id, layer=layer)
        _after_approval(svc, project, "scenarios", layer)
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
            values = edit_fields(f"sc_{scenario.scenario_id}", scenario.model_dump(), _spec(SCENARIO_SPEC, layer))
            if st.button("Save changes", key=f"sc_save_{scenario.scenario_id}"):
                safe(lambda: svc.scenarios.edit(project.id, Scenario.model_validate({**scenario.model_dump(), **values})))
                notify("Scenario saved. It needs approval again.")
                st.rerun()
    _ai_change(svc, project, "scenarios", "sc", ids, lambda text, scope, ctx: svc.scenarios.modify(project, text, scope, on_event=ctx.on_event, progress=ctx.reporter, layer=layer))
    with st.expander("Add a scenario manually"):
        with st.form("sc_manual"):
            values = edit_fields("sc_new", {}, _spec(SCENARIO_SPEC, layer))
            if st.form_submit_button("Add scenario") and values["title"].strip():
                safe(lambda: svc.scenarios.add_manual(project, layer=layer, **values))
                st.rerun()
    _download("Download scenarios (Excel)", scenarios_workbook(project, scenarios, svc.repo.list_test_cases(project.id, layer=layer)), f"{project.name}_scenarios.xlsx")


def render_test_cases(svc: Services) -> None:
    project = require_project(svc)
    theme.page_header("Test cases", "Detailed, automatable test cases expanded from the approved scenarios.", "STEP 03 // TEST CASES")
    show_notices()
    layer = layer_switch(project, "testcases")
    if jobs_ui.running_panel(svc, project, ("testcases",), "Test case design in progress"):
        return
    jobs_ui.last_problem(svc, project, ("testcases",))
    if stop_if_unsupported(layer):
        return
    approved_scenarios = svc.repo.list_scenarios(project.id, status="approved", layer=layer)
    cases = svc.repo.list_test_cases(project.id, layer=layer)
    if not approved_scenarios:
        st.info("Approve at least one scenario first. Test cases are generated only from approved scenarios.")
        return
    with st.expander("Generate test cases", expanded=not cases):
        requirements = st.text_area("Extra requirements (optional)", key="tc_req", height=80)
        st.caption(f"{len(approved_scenarios)} approved scenario(s) will be expanded into detailed test cases.")
        if st.button("Generate test cases", type="primary"):
            def work(ctx):  # noqa: ANN001, ANN202
                return {"count": len(svc.testcases.generate(project, requirements, on_event=ctx.on_event, progress=ctx.reporter, layer=layer))}

            jobs_ui.start_job(
                svc, project, "testcases", f"Designing {layer_label(layer)} test cases" if len(project.layers) > 1 else "Designing test cases", guarded(layer, work),
                notice="{count} test cases generated. Review and approve them.",
            )
    if not cases:
        return

    approved = sum(c.status == "approved" for c in cases)
    a, b, c, d = st.columns(4)
    a.metric("Test cases", len(cases))
    b.metric("Approved", approved)
    c.metric("Automatable", sum(t.automation_candidate for t in cases))
    d.metric("Scenarios covered", len({t.scenario_id for t in cases}))
    columns = {"ID": "test_case_id", "Scenario": "scenario_id", "Module": "module", "Title": "title", "Type": "test_type", "Priority": "priority", "Automatable": "automation_candidate", "Status": "status"}
    if layer == "api":
        columns = {**columns, "Endpoint": "related_page"}
    event = st.dataframe(_frame(cases, columns), hide_index=True, width="stretch", on_select="rerun", selection_mode="multi-row", key=f"tc_table_{layer}")
    ids = selected_rows(event, [t.test_case_id for t in cases])

    a, b, c, d = st.columns(4)
    if a.button(f"Approve selected ({len(ids)})", disabled=not ids):
        svc.testcases.approve(project.id, ids)
        _after_approval(svc, project, "testcases", layer)
    if b.button("Approve all"):
        svc.testcases.approve_all(project.id, layer=layer)
        _after_approval(svc, project, "testcases", layer)
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
            values = edit_fields(f"tc_{case.test_case_id}", case.model_dump(), _spec(CASE_SPEC, layer))
            requests_json = ""
            if layer == "api":
                st.caption("The HTTP requests this test sends (JSON). Saved values are used as {{var.name}}, secrets as {{env:NAME}}, a saved connection by name in \"auth\".")
                requests_json = st.text_area("API requests (JSON)", value=json.dumps(case.api.model_dump(by_alias=True, exclude_none=True) if case.api else {"requests": []}, indent=2), height=260, key=f"tc_api_{case.test_case_id}")
            if st.button("Save changes", key=f"tc_save_{case.test_case_id}"):
                edited = _edited_case(svc, project, case, values, requests_json, layer)
                if edited is not None:
                    safe(lambda: svc.testcases.edit(project.id, edited))
                    notify("Test case saved. It needs approval again.")
                    st.rerun()
    _ai_change(svc, project, "testcases", "tc", ids, lambda text, scope, ctx: svc.testcases.modify(project, text, scope, on_event=ctx.on_event, progress=ctx.reporter, layer=layer))
    with st.expander("Add a test case manually"):
        scenario_ids = [s.scenario_id for s in svc.repo.list_scenarios(project.id, layer=layer)]
        with st.form("tc_manual"):
            scenario_id = st.selectbox("Scenario", scenario_ids)
            values = edit_fields("tc_new", {}, _spec(CASE_SPEC, layer))
            if st.form_submit_button("Add test case") and values["title"].strip():
                safe(lambda: svc.testcases.add_manual(project.id, scenario_id=scenario_id, layer=layer, **values))
                st.rerun()
    scenarios = svc.repo.list_scenarios(project.id, layer=layer)
    a, b = st.columns(2)
    with a:
        _download("Download test cases (Excel)", cases_workbook(project, scenarios, cases), f"{project.name}_test_cases.xlsx")
    with b:
        _download("Download scenarios + test cases + summary (Excel)", combined_workbook(project, scenarios, cases), f"{project.name}_test_design.xlsx")
