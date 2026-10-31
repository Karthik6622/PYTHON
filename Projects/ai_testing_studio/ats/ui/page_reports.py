"""Reports page: build an execution report with an AI summary and download it in several formats."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ats.reporting.exporters import report_html, report_json, report_workbook, report_zip
from ats.services import Services
from ats.ui.session import require_project, safe, show_notices
from ats.workflow import IN_PROGRESS_STATUSES


def render(svc: Services) -> None:
    project = require_project(svc)
    st.header("Reports")
    show_notices()
    executions = [e for e in svc.repo.list_executions(project.id, ("full",)) if e["status"] not in IN_PROGRESS_STATUSES]
    if not executions:
        st.info("A report needs a finished execution.")
        return
    labels = {e["id"]: f"Run #{e['run_number']} - {e['status']} - {e['started_at'][:19]}" for e in executions}
    execution_id = st.selectbox("Execution", list(labels), format_func=labels.get)
    with_ai = st.checkbox("Write the summary with the AI model", value=True, help="Without it, a deterministic summary is used.")
    if st.button("Build report", type="primary"):
        with st.spinner("Building the report..."):
            report = safe(lambda: svc.reports.build(project, execution_id, with_ai=with_ai))
        if report:
            st.session_state.setdefault("reports", {})[(project.id, execution_id)] = report
    report = st.session_state.get("reports", {}).get((project.id, execution_id))
    if not report:
        st.caption("Build the report to preview and download it.")
        return

    totals, summary = report["totals"], report["summary"]
    cols = st.columns(6)
    for col, (label, key) in zip(cols, [("Total", "total"), ("Passed", "passed"), ("Failed", "failed"), ("Healed", "healed"), ("Inconclusive", "inconclusive"), ("Pass rate %", "pass_rate")], strict=True):
        col.metric(label, totals.get(key, 0))
    st.subheader("Executive summary" + (" (AI-written)" if summary.get("ai_generated") else " (generated from the numbers)"))
    st.write(summary.get("summary", ""))
    left, right = st.columns(2)
    for column, title, key in ((left, "Highlights", "highlights"), (right, "Risks", "risks")):
        with column:
            st.markdown(f"**{title}**")
            for item in summary.get(key, []):
                st.markdown(f"- {item}")
    if summary.get("recommendations"):
        st.markdown("**Recommendations**")
        for item in summary["recommendations"]:
            st.markdown(f"- {item}")

    tabs = st.tabs(["By module", "Traceability", "Defects", "Healing", "History"])
    for tab, key in zip(tabs, ["by_module", "traceability", "defects", "healings", "history"], strict=True):
        with tab:
            rows = report.get(key) or []
            if isinstance(rows, dict):
                rows = [{"name": k, **v} if isinstance(v, dict) else {"name": k, "value": v} for k, v in rows.items()]
            if rows:
                st.dataframe(pd.json_normalize(rows).astype(str), hide_index=True, width="stretch")
            else:
                st.caption("Nothing to show.")

    st.subheader("Download")
    execution = report["execution"]
    stem = f"{project.name}_run{execution['run_number']}".replace(" ", "_")
    evidence = svc.reports.evidence_files(project.id, execution)
    a, b, c, d = st.columns(4)
    a.download_button("HTML report", report_html(report, evidence), file_name=f"{stem}.html", mime="text/html")
    b.download_button("Excel workbook", report_workbook(report), file_name=f"{stem}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    c.download_button("JSON", report_json(report), file_name=f"{stem}.json", mime="application/json")
    d.download_button("ZIP with evidence", report_zip(report, evidence), file_name=f"{stem}.zip", mime="application/zip")
    st.caption("Reports are masked: credentials and tokens are never included.")
