"""Results page: per-test outcomes, failure analysis, evidence, self-healing review and defect drafts."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from ats.execution.executor import run_dir
from ats.services import Services
from ats.ui.page_execute import live_run
from ats.ui.session import notify, require_project, safe, show_notices
from ats.ui.widgets import chip, selected_rows
from ats.workflow import IN_PROGRESS_STATUSES

FAILURES = {"FAIL", "INCONCLUSIVE"}


def session_secrets() -> dict[str, str]:
    """Run-time values the person typed on the Execute page in this browser session."""
    return {k.removeprefix("secret_"): v for k, v in st.session_state.items() if k.startswith("secret_") and isinstance(v, str) and v}


def locator_text(data: dict) -> str:
    if not data:
        return ""
    name = f", name={data['name']!r}" if data.get("name") else ""
    return f"{data.get('kind')}: {data.get('value')}{name}"


def evidence_image(project_id: str, execution_id: str, evidence: dict) -> str | None:
    rel = evidence.get("screenshot")
    if not rel:
        return None
    base = (run_dir(project_id, execution_id) / "workspace").resolve()
    path = (base / rel).resolve()
    return str(path) if base in path.parents and path.is_file() else None


def render_detail(svc: Services, project, execution: dict, row: dict) -> None:
    analysis, evidence = row.get("analysis") or {}, row.get("evidence") or {}
    st.markdown(f"### {row['test_case_id']} {chip(row['status'])}")
    if row["message"]:
        st.code(row["message"][:1500], language="text")
    left, right = st.columns([3, 2])
    with left:
        if analysis:
            st.markdown(f"**Category:** {analysis.get('category', 'UNKNOWN')} (confidence {float(analysis.get('confidence', 0)):.0%})" + (" | AI-assisted" if analysis.get("ai_used") else " | rule-based"))
            if analysis.get("summary"):
                st.write(analysis["summary"])
            if analysis.get("reasoning"):
                with st.expander("Reasoning"):
                    st.write(analysis["reasoning"])
            if analysis.get("recommended_action"):
                st.info(f"Recommended: {analysis['recommended_action']}")
            for note in analysis.get("notes", []):
                st.caption(note)
            check = analysis.get("locator_check") or {}
            if check:
                st.caption(f"Locator check on the failing page: {json.dumps(check)[:300]}")
        else:
            st.caption("No analysis has been recorded for this test.")
        steps = evidence.get("steps") or []
        if steps:
            st.markdown("**Executed steps**")
            for step in steps:
                icon = {"passed": "✅", "failed": "❌"}.get(step.get("status"), "•")
                st.markdown(f"{icon} {step.get('index')}. {step.get('description')}" + (f" `{step['element']}`" if step.get("element") else ""))
    with right:
        image = evidence_image(project.id, execution["id"], evidence)
        if image:
            st.image(image, caption="Screenshot at failure")
    if row["status"] in FAILURES:
        if st.button("Draft a defect report", key=f"defect_{row['test_case_id']}"):
            if safe(lambda: svc.analysis.draft_defect(project, execution["id"], row["test_case_id"])):
                notify(f"Defect drafted for {row['test_case_id']}.")
                st.rerun()


@st.fragment(run_every="3s")
def healing_panel(svc: Services, project, execution_id: str) -> None:
    records = svc.repo.list_healings(project.id, execution_id)
    if not records:
        return
    st.subheader("Self-healing")
    st.caption("A fix is only a proposal until the affected tests pass again with it. Healed tests are counted separately from passed tests.")
    token = svc.tokens.get(project.id)
    for record in records:
        title = f"{record['element_key']} {chip(record['status'])} confidence {record['confidence']:.2f} | tests: {', '.join(record['test_case_ids'])}"
        with st.expander(title, expanded=record["status"] in {"proposed", "verified"}):
            a, b = st.columns(2)
            a.markdown("**Current locator**")
            a.code(locator_text(record["old_locator"]), language="text")
            b.markdown("**Proposed locator**")
            b.code(locator_text(record["new_locator"]), language="text")
            st.write(record["reason"])
            if record["outcome"]:
                st.caption(f"Outcome: {record['outcome']}")
            if record["validation"]:
                st.caption("Checked against the failing page: " + json.dumps(record["validation"])[:300])
            if record["proposed_code"]:
                st.code(record["proposed_code"], language="diff")
            status, key = record["status"], f"heal_{record['id']}"
            cols = st.columns(4)
            if status == "proposed":
                if cols[0].button("Approve and verify", key=f"{key}_a", type="primary"):
                    safe(lambda: svc.healer.approve(record["id"], project, session_secrets()))
                    st.rerun()
            if status == "verified":
                if cols[0].button("Apply to project", key=f"{key}_ap", type="primary"):
                    diff = safe(lambda: svc.healer.apply(record["id"], project))
                    if diff is not None:
                        notify("Applied to the stored automation project and the locator repository.")
                        st.rerun()
                if cols[1].button("Open pull request", key=f"{key}_pr", disabled=not token, help="Needs a GitHub token (GitHub page)."):
                    ctx = safe(lambda: svc.analysis.context_for(project, execution_id))
                    url = safe(lambda: svc.github.open_healing_pr(ctx, [record["id"]], token)) if ctx else None
                    if url:
                        notify(f"Pull request opened: {url}")
                        st.rerun()
            if status in {"proposed", "verified"} and cols[2].button("Reject", key=f"{key}_r"):
                svc.healer.reject(record["id"], project)
                st.rerun()
            if status == "running":
                st.info("Re-running the affected tests with this fix...")
            if record["pr_url"]:
                st.markdown(f"[Pull request]({record['pr_url']})")


def defects_panel(svc: Services, project, execution_id: str) -> None:
    defects = svc.repo.list_defects(project.id, execution_id)
    if not defects:
        return
    st.subheader("Draft defects")
    st.caption("Drafts are advice for a person to review; nothing is filed automatically.")
    for item in defects:
        d = item["data"]
        with st.expander(f"{d.get('defect_id')} - {d.get('title')} ({d.get('severity')})"):
            st.write(d.get("description", ""))
            st.markdown("**Steps to reproduce**")
            for number, step in enumerate(d.get("steps_to_reproduce", []), 1):
                st.markdown(f"{number}. {step}")
            a, b = st.columns(2)
            a.markdown(f"**Expected**: {d.get('expected_result', '')}")
            b.markdown(f"**Actual**: {d.get('actual_result', '')}")
            env = d.get("environment", {})
            st.caption(" | ".join(f"{k}: {v}" for k, v in env.items() if v))
            st.download_button("Download defect (JSON)", json.dumps(d, indent=2, ensure_ascii=False), file_name=f"{d.get('defect_id', 'defect')}.json", mime="application/json", key=f"dl_{item['id']}")


def render(svc: Services) -> None:
    project = require_project(svc)
    st.header("Results and analysis")
    show_notices()
    executions = svc.repo.list_executions(project.id, ("full",))
    if not executions:
        st.info("No execution yet. Run the tests first.")
        return
    labels = {e["id"]: f"Run #{e['run_number']} - {e['status']} - {e['started_at'][:19]}" for e in executions}
    execution_id = st.selectbox("Execution", list(labels), format_func=labels.get)
    execution = svc.repo.get_execution(execution_id)
    if execution["status"] in IN_PROGRESS_STATUSES:
        live_run(svc, project.id, execution_id)
        return
    if execution["status"] in {"error", "cancelled"} or execution.get("error"):
        st.error(execution.get("error") or "The run did not finish.")

    totals = execution["totals"] or {}
    cols = st.columns(7)
    for col, (label, key) in zip(cols, [("Total", "total"), ("Passed", "passed"), ("Failed", "failed"), ("Healed", "healed"), ("Inconclusive", "inconclusive"), ("Skipped", "skipped"), ("Pass rate %", "pass_rate")], strict=True):
        col.metric(label, totals.get(key, 0))
    results = svc.repo.list_results(execution_id)
    if not results:
        return
    cases = {c.test_case_id: c for c in svc.repo.list_test_cases(project.id)}
    statuses = sorted({r["status"] for r in results})
    wanted = st.multiselect("Show", statuses, default=statuses)
    shown = [r for r in results if r["status"] in wanted]
    table = pd.DataFrame(
        [{"Test case": r["test_case_id"], "Title": cases[r["test_case_id"]].title if r["test_case_id"] in cases else r["test_name"], "Status": r["status"], "Seconds": round(r["duration"], 1),
          "Category": (r.get("analysis") or {}).get("category", ""), "Message": r["message"][:120]} for r in shown]
    )  # fmt: skip
    event = st.dataframe(table, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key=f"res_{execution_id}")
    picked = selected_rows(event, [r["test_case_id"] for r in shown])
    if picked:
        render_detail(svc, project, execution, next(r for r in shown if r["test_case_id"] == picked[0]))
    else:
        st.caption("Select a row to see the analysis, steps and screenshot.")

    failing = [r for r in results if r["status"] in FAILURES]
    if failing and not any(r.get("analysis") for r in failing):
        if st.button("Analyze failures now"):
            with st.spinner("Analyzing failures..."):
                safe(lambda: svc.analysis.reanalyze(project, execution_id, session_secrets()))
            st.rerun()
    healing_panel(svc, project, execution_id)
    defects_panel(svc, project, execution_id)
