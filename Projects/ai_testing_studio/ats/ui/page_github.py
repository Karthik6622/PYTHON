"""GitHub page: link a repository, import tests, commit the generated project to a new branch and open a pull request."""

from __future__ import annotations

import streamlit as st

from ats.config import get_settings
from ats.security import token_hint
from ats.services import Services
from ats.ui.session import notify, require_project, safe, show_notices


def imported_files(project_id: str) -> tuple[dict[str, str], str] | None:
    return st.session_state.get("gh_import", {}).get(project_id)


def render(svc: Services) -> None:
    project = require_project(svc)
    st.header("GitHub")
    show_notices()
    st.write("Link a repository to commit generated tests to a **new branch** (never the default branch) and open a pull request, or import existing tests to run them.")

    token = svc.tokens.get(project.id)
    with st.container(border=True):
        st.subheader("Access token")
        if token:
            st.success(f"A token ({token_hint(token)}) is held in memory for this project. It is not saved to disk or the database.")
            if st.button("Forget the token"):
                svc.tokens.clear(project.id)
                st.rerun()
        else:
            entered = st.text_input("Personal access token", type="password", help="Needs repository read and write (contents, pull requests). Kept in memory only.")
            if st.button("Use this token", disabled=not entered):
                svc.tokens.set(project.id, entered)
                st.rerun()
            if get_settings().github_token:
                if st.button("Use GITHUB_TOKEN from the server environment"):
                    svc.tokens.set(project.id, get_settings().github_token)
                    st.rerun()

    link = svc.repo.get_github(project.id) or {}
    st.subheader("Repository")
    repo_url = st.text_input("Repository URL", value=link.get("repo_url", ""), placeholder="https://github.com/owner/repo")
    if st.button("Verify and link", disabled=not (repo_url and token)):
        info = safe(lambda: svc.github.link(project, repo_url, token))
        if info:
            notify(f"Linked {info['full_name']} (default branch {info['default_branch']}). {'You can push.' if info['can_push'] else 'This token is read-only.'}")
            st.rerun()
    if not link.get("repo_url"):
        st.info("Link a repository to continue.")
        return
    st.caption(f"Linked: {link['repo_url']} | default branch: {link.get('default_branch') or 'unknown'}")

    st.subheader("Commit generated tests")
    bundle = svc.repo.latest_bundle(project.id)
    if not bundle:
        st.info("Generate and approve the automation project first.")
    else:
        if bundle["status"] == "draft":
            st.warning("The latest automation project is not approved yet. Review and approve it first for best results.")
        a, b = st.columns(2)
        base = a.text_input("Base branch", value=link.get("default_branch") or "main")
        branch = b.text_input("New branch name (optional)", placeholder="ai-tests/<generated>")
        prefix = st.text_input("Folder in the repository (optional)", placeholder="e2e")
        open_pr = st.checkbox("Open a pull request", value=True)
        if st.button("Commit to a new branch", type="primary", disabled=not token):
            result = safe(lambda: svc.github.commit_bundle(project, bundle["id"], token, open_pr=open_pr, branch=branch, base_branch=base, path_prefix=prefix))
            if result:
                notify(f"Committed {result['files']} files to {result['branch']}. " + (f"Pull request: {result['pr_url']}" if result["pr_url"] else f"Branch: {result.get('branch_url', '')}"))
                st.rerun()
        if not token:
            st.caption("Enter a token above to enable committing.")
    if link.get("branch"):
        st.markdown(f"Last commit: branch `{link['branch']}`" + (f" | [commit]({link['commit_url']})" if link.get("commit_url") else "") + (f" | [pull request]({link['pr_url']})" if link.get("pr_url") else ""))

    st.subheader("Import existing tests")
    ref = st.text_input("Branch, tag or commit to import", value=link.get("branch") or link.get("default_branch") or "main", key="import_ref")
    if st.button("Download from GitHub", disabled=not token):
        outcome = safe(lambda: svc.github.import_tests(project, token, ref))
        if outcome:
            st.session_state.setdefault("gh_import", {})[project.id] = outcome
            notify(f"Imported {len(outcome[0])} files from {outcome[1]}. Choose 'Imported from GitHub' on the Execute page.")
            st.rerun()
    imported = imported_files(project.id)
    if imported:
        st.success(f"{len(imported[0])} files imported from `{imported[1]}` are ready to run.")
