"""GitHub page: link a repository, publish the generated project to its own clean branch, import tests."""

from __future__ import annotations

import re
from datetime import datetime

import streamlit as st

from ats.config import get_settings
from ats.security import token_hint
from ats.services import Services
from ats.ui import theme
from ats.ui.session import go_to, notify, require_project, safe, show_notices


def imported_files(project_id: str) -> tuple[dict[str, str], str] | None:
    return st.session_state.get("gh_import", {}).get(project_id)


def publish_panel(svc: Services, project, token: str, link: dict) -> None:  # noqa: ANN001
    """Publish every channel of the project (Web / Mobile / API) to ONE repository + branch. An existing branch is inspected first and only
    the channels that are missing are added: files the studio did not generate are never touched."""
    from ats.models import CHANNEL_LAYER, CHANNEL_LABELS

    st.subheader("Publish to a repository branch")
    bundles = {c: svc.repo.latest_bundle(project.id, layer=CHANNEL_LAYER[c]) for c in project.channels}
    ready = {c: b["id"] for c, b in bundles.items() if b}
    for channel, bundle in bundles.items():
        if not bundle:
            st.caption(f"➕ {CHANNEL_LABELS[channel]}: no automation project generated yet.")
    if not ready:
        st.info("Generate the automation project first.")
        return
    repo_url = link.get("repo_url", "")
    branches = safe(lambda: svc.github.branches(project, token), []) if token else []
    mode = st.radio("Branch", ["Create a new clean branch", "Use an existing branch"], horizontal=True, key="gh_branch_mode")
    if mode == "Use an existing branch":
        default = branches.index(link["branch"]) if link.get("branch") in branches else 0
        branch = st.selectbox("Existing branch", branches, index=default if branches else None, placeholder="Link the repository and enter a token") if branches else st.text_input("Existing branch", value=link.get("branch", ""))
        create = False
    else:
        slug = re.sub(r"[^a-z0-9]+", "-", project.name.lower()).strip("-")[:30] or "project"
        branch = st.text_input("New branch name", value=f"ai-tests/{slug}-{datetime.now().strftime('%Y%m%d')}", key=f"gh_new_branch_{project.id}", help="Created empty: it holds only your test project, nothing from main.")
        create = True
    chosen = st.multiselect("Channels to publish", list(ready), default=list(ready), format_func=CHANNEL_LABELS.get)
    selected = {c: ready[c] for c in chosen}
    st.caption(f"Workspace = repository + branch: `{repo_url}` @ `{branch or '...'}`. Branch names are only unique inside one repository.")
    if not (token and branch and selected):
        st.caption("Enter a token, choose a branch and at least one channel to continue.")
        return
    preview = safe(lambda: svc.github.preview(project, selected, token, repo_url, branch))
    if preview is None:
        return
    if preview.problem:
        st.error(preview.problem)
        return
    st.markdown("**Existing automation on this branch**")
    st.markdown("  \n".join(f"{'✅' if preview.info.channels[c].existing else '➕'} {CHANNEL_LABELS[c]} " + ("existing" if preview.info.channels[c].existing else "not configured") for c in CHANNEL_LABELS))
    if preview.will_create:
        st.info("The branch does not exist: a new clean branch (only your test project, nothing from main) will be created.")
    summary = preview.plan.summary()
    a, b, c, d = st.columns(4)
    a.metric("Files to add", summary["add"])
    b.metric("Files to update", summary["update"])
    c.metric("Existing files kept", summary["keep"])
    d.metric("Shared files merged", summary["shared"])
    for conflict in preview.plan.conflicts:
        st.warning(f"{conflict.path}: {conflict.message}")
    for item in preview.plan.shared:
        if item.action != "unchanged":
            st.caption(f"{item.path}: {item.action} ({item.detail})")
    if st.button("Publish to this branch", type="primary", key="gh_publish"):
        with st.spinner("Publishing to GitHub..."):
            result = safe(lambda: svc.github.publish(project, selected, token, repo_url, branch, create_if_missing=create))
        if result:
            notify(f"Published {', '.join(CHANNEL_LABELS[c] for c in result['channels'])} to `{result['branch']}`: {len(result['added'])} added, {len(result['updated'])} updated. Run the tests next.")
            go_to("execute")  # GitHub comes right before Execute
            st.rerun()


def render(svc: Services) -> None:
    project = require_project(svc)
    theme.page_header("GitHub", "Publish the generated tests to their own branch, then run them. Automatic fixes are pushed to the same branch.", "STEP 05 // GITHUB")
    show_notices()
    st.write(
        "Link a repository to publish the generated tests to a **new, clean branch**: it contains only your test project, none of the files "
        "of `main` or any other branch, and the default branch is never touched. Import existing tests to run them instead."
    )

    if st.button("Skip GitHub and run the tests", key="gh_skip"):
        svc.repo.audit(project.id, "user", "github.skipped", "github", {})
        notify("GitHub skipped. Run the tests next.")
        go_to("execute")
        st.rerun()

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
            if st.button("Use this token"):
                if entered.strip():
                    svc.tokens.set(project.id, entered.strip())
                    st.rerun()
                st.warning("Paste a personal access token first.")
            if get_settings().github_token:
                if st.button("Use GITHUB_TOKEN from the server environment"):
                    svc.tokens.set(project.id, get_settings().github_token)
                    st.rerun()

    link = svc.repo.get_github(project.id) or {}
    st.subheader("Repository")
    repo_url = st.text_input("Repository URL", value=link.get("repo_url", ""), placeholder="https://github.com/owner/repo")
    if st.button("Verify and link"):
        if not (repo_url.strip() and token):
            st.warning("Enter the repository URL and a token first.")
        else:
            info = safe(lambda: svc.github.link(project, repo_url.strip(), token))
            if info:
                notify(f"Linked {info['full_name']} (default branch {info['default_branch']}). {'You can push.' if info['can_push'] else 'This token is read-only.'}")
                st.rerun()
    if not link.get("repo_url"):
        st.info("Link a repository to continue.")
        return
    st.caption(f"Linked: {link['repo_url']} | default branch: {link.get('default_branch') or 'unknown'}")

    publish_panel(svc, project, token, link)

    with st.expander("Advanced: commit from an existing branch and open a pull request"):
        bundle = svc.repo.latest_bundle(project.id)
        if not bundle:
            st.info("Generate and approve the automation project first.")
        else:
            if bundle["status"] == "draft":
                st.warning("The latest automation project is not approved yet. Review and approve it first for best results.")
            branch = st.text_input("Branch name (optional)", placeholder="ai-tests/<generated>", help="A new branch is created. Publishing again updates the same branch.")
            prefix = st.text_input("Folder in the repository (optional)", placeholder="e2e")
            with st.container(border=True):
                st.caption("Keeps all files of that branch and lets you open a pull request. The default option (clean branch) cannot have a pull request because it shares no history.")
                keep_base = st.checkbox("Create the branch from an existing branch", value=False)
                base = st.text_input("Base branch", value=link.get("default_branch") or "main", disabled=not keep_base)
                open_pr = st.checkbox("Open a pull request", value=True, disabled=not keep_base)
            if st.button("Publish to a clean branch" if not keep_base else "Commit to a new branch", type="primary", disabled=not token):
                with st.spinner("Publishing to GitHub..."):
                    result = safe(
                        lambda: svc.github.commit_bundle(
                            project, bundle["id"], token, open_pr=keep_base and open_pr, branch=branch, base_branch=base, path_prefix=prefix, orphan=not keep_base
                        )
                    )
                if result:
                    notify(f"Published {result['files']} files to branch {result['branch']}. Run the tests next.")
                    go_to("execute")
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
