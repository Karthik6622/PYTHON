"""Open a folder from the visitor's own computer, and keep it in sync, when the app is hosted (Streamlit Cloud, a server).

A hosted app cannot show the operating system's folder window itself, but the visitor's browser can: it asks for a folder
(File System Access API: Chrome, Edge, Opera), reads the text files and sends them to the server, and later writes back every
file that was created or changed in the workspace. The server half is studio/services/local_sync.py."""

from __future__ import annotations

import streamlit as st

from studio.config import settings
from studio.services import folders, local_sync
from studio.services.repository_service import RepositoryError

from .state import log, open_workspace, repo, repositories, window_id

_JS = r"""
let api = null;
let cfg = null;
let handle = null;
let status = "";
let draw = () => {};
const seen = new Set();
const SENSITIVE = /^(\.env(\..+)?|.*\.(pem|key|p12|pfx)|id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|\.npmrc|\.pypirc|credentials(\.json)?)$/i;
const TEMPLATES = new Set([".env.example", ".env.sample", ".env.template", ".env.dist"]);

function say(text) { status = text; draw(); }

async function pick() {
  try {
    return await window.showDirectoryPicker({ id: "rk-studio", mode: "readwrite" });
  } catch (error) {
    if (error && error.name !== "AbortError") say("Could not open the folder: " + (error.message || error));
    return null;
  }
}

async function walk(dir, prefix, files, stats) {
  for await (const [name, entry] of dir.entries()) {
    if (files.length >= cfg.max_files || stats.bytes > cfg.max_total) { stats.truncated = true; return; }
    if (entry.kind === "directory") {
      if (!cfg.skip.includes(name)) await walk(entry, prefix + name + "/", files, stats);
      continue;
    }
    const dot = name.lastIndexOf(".");
    const ext = dot > 0 ? name.slice(dot).toLowerCase() : "";
    if (cfg.binary.includes(ext) || (SENSITIVE.test(name) && !TEMPLATES.has(name.toLowerCase()))) { stats.skipped++; continue; }
    const file = await entry.getFile();
    if (file.size > cfg.max_file) { stats.skipped++; continue; }
    const text = await file.text();
    if (text.includes("\u0000") || text.includes("\ufffd")) { stats.skipped++; continue; }
    files.push({ path: prefix + name, content: text });
    stats.bytes += file.size;
  }
}

async function openFolder() {
  const chosen = await pick();
  if (!chosen) return;
  say("Reading " + chosen.name + " ...");
  const files = [];
  const stats = { bytes: 0, skipped: 0, truncated: false };
  try {
    await walk(chosen, "", files, stats);
  } catch (error) {
    say("Could not read the folder: " + (error.message || error));
    return;
  }
  handle = chosen;
  say("Sending " + files.length + " files ...");
  api.setTriggerValue("opened", { name: chosen.name, files, skipped: stats.skipped, truncated: stats.truncated, nonce: Math.random() });
}

async function saveToFolder() {
  const chosen = await pick();
  if (!chosen) return;
  let filled = false;
  for await (const _ of chosen.values()) { filled = true; break; }
  if (filled && !window.confirm("\"" + chosen.name + "\" is not empty. Files with the same names will be replaced by the files from this workspace. Continue?")) return;
  handle = chosen;
  say("Saving to " + chosen.name + " ...");
  api.setTriggerValue("linked", { name: chosen.name, nonce: Math.random() });
}

function stop() {
  handle = null;
  say("");
  api.setTriggerValue("stopped", { nonce: Math.random() });
}

async function directory(parts, create) {
  let dir = handle;
  for (const part of parts) dir = await dir.getDirectoryHandle(part, { create });
  return dir;
}

async function flush(batch) {
  const failed = [];
  say("Saving " + (batch.writes.length + batch.deletes.length) + " change(s) to " + cfg.name + " ...");
  for (const item of batch.writes) {
    try {
      const parts = item.path.split("/");
      const leaf = parts.pop();
      const file = await (await directory(parts, true)).getFileHandle(leaf, { create: true });
      const out = await file.createWritable();
      await out.write(item.content);
      await out.close();
    } catch (error) { failed.push(item.path); }
  }
  for (const path of batch.deletes) {
    try {
      const parts = path.split("/");
      const leaf = parts.pop();
      await (await directory(parts, false)).removeEntry(leaf);
    } catch (error) { if (!error || error.name !== "NotFoundError") failed.push(path); }
  }
  say(failed.length ? failed.length + " file(s) could not be written. Check the folder permissions." : "All changes saved to " + cfg.name + ".");
  api.setTriggerValue("synced", { id: batch.id, failed, nonce: Math.random() });
}

export default function (component) {
  api = component;
  cfg = component.data;
  const host = component.parentElement;
  let box = host.querySelector(".rk");
  if (!box) { box = document.createElement("div"); box.className = "rk"; host.appendChild(box); }

  const button = (label, onClick, primary) => {
    const item = document.createElement("button");
    item.type = "button";
    item.textContent = label;
    item.className = primary ? "primary" : "";
    item.onclick = onClick;
    return item;
  };
  draw = () => {
    const parts = [];
    if (typeof window.showDirectoryPicker !== "function") {
      const note = document.createElement("span");
      note.className = "note";
      note.textContent = "Open folders from your computer: use Chrome or Edge (or upload files in the Explorer).";
      parts.push(note);
    } else if (cfg.linked && handle) {
      const live = document.createElement("span");
      live.className = "live";
      live.textContent = "Synced with " + cfg.name;
      live.title = status || "Changes made here are saved to this folder on your computer.";
      parts.push(live, button("Stop", stop, false));
    } else if (cfg.linked) {
      parts.push(button("Reconnect " + cfg.name, openFolder, true));
    } else {
      parts.push(
        button("Open folder", openFolder, true),
        button("Save to folder", saveToFolder, false),
      );
    }
    if (status && !(cfg.linked && handle)) {
      const text = document.createElement("span");
      text.className = "note";
      text.textContent = status;
      parts.push(text);
    }
    box.replaceChildren(...parts);
  };
  draw();

  const batch = cfg.outbox;
  if (batch && handle && !seen.has(batch.id)) {
    seen.add(batch.id);
    flush(batch);
  }
}
"""

_CSS = """
.rk { display:flex; align-items:center; gap:8px; flex-wrap:nowrap; font:12.5px/1.2 "Segoe UI", system-ui, sans-serif; color:#dde6ff; min-height:36px; }
button { cursor:pointer; border:1px solid rgba(139,92,246,.55); background:rgba(139,92,246,.12); color:#dde6ff; border-radius:999px;
  padding:6px 14px; font:inherit; font-weight:600; white-space:nowrap; transition:background .15s, box-shadow .15s; }
button:hover { background:rgba(139,92,246,.3); box-shadow:0 0 12px rgba(139,92,246,.45); }
button.primary { background:linear-gradient(90deg,#22d3ee,#8b5cf6); border-color:transparent; color:#06101f; }
.live { display:inline-flex; align-items:center; gap:7px; padding:6px 12px; border-radius:999px; border:1px solid rgba(52,211,153,.5); background:rgba(52,211,153,.1); color:#34d399; font-weight:600; white-space:nowrap; max-width:260px; overflow:hidden; text-overflow:ellipsis; }
.live::before { content:""; width:7px; height:7px; border-radius:50%; background:#34d399; box-shadow:0 0 8px #34d399; flex:none; }
.note { color:#7886ad; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
"""

_component = None
try:
    _component = st.components.v2.component("rk_local_folder", js=_JS, css=_CSS)
except Exception:  # Streamlit older than components v2: the upload / download buttons in the Explorer still work
    _component = None

_KEY = "rk_local"


def available() -> bool:
    """The browser folder feature is for hosted deployments; on the user's own computer the operating system's dialog is used."""
    return _component is not None and not folders.native_picker_available()


def _event(name: str) -> dict:
    state = st.session_state.get(_KEY)
    value = getattr(state, name, None) if state is not None else None
    if value is None and isinstance(state, dict):
        value = state.get(name)
    return value if isinstance(value, dict) else {}


def _notify(text: str, icon: str = ":material/info:") -> None:
    """Callbacks must not draw anything, so messages wait here until the panel runs."""
    log(text)
    st.session_state["_local_notice"] = (text, icon)


def _on_opened() -> None:
    event = _event("opened")
    name = local_sync.clean_name(event.get("name"))
    destination = (settings.workspace_path / "local" / window_id() / name).resolve()
    try:
        count = local_sync.import_files(destination, event.get("files"))
        folder = repositories.open_scratch(str(destination))
    except (local_sync.SyncError, RepositoryError) as exc:
        _notify(getattr(exc, "message", None) or str(exc), ":material/error:")
        return
    open_workspace(folder)
    st.session_state["_link"] = local_sync.LocalLink(name, known=local_sync.scan(destination))
    st.session_state["_reload_all"] = True
    extra = " Some large, binary or secret files were left out." if event.get("skipped") else ""
    if event.get("truncated"):
        extra += " The folder is large, so only part of it was opened."
    _notify(f"Opened {name}: {count} files.{extra}", ":material/folder_open:")


def _on_linked() -> None:
    event = _event("linked")
    name = local_sync.clean_name(event.get("name"))
    st.session_state["_link"] = local_sync.LocalLink(name)
    st.session_state["_reload_all"] = True
    _notify(f"Saving this workspace to {name} on your computer.", ":material/save:")


def _on_synced() -> None:
    event = _event("synced")
    link = st.session_state.get("_link")
    if link is not None:
        link.acknowledge(event.get("id"))
    failed = event.get("failed")
    if failed:
        _notify(f"{len(failed)} file(s) could not be saved to your folder.", ":material/error:")


def _on_stopped() -> None:
    st.session_state.pop("_link", None)
    st.session_state["_reload_all"] = True
    _notify("Stopped saving to your computer.")


def _panel() -> None:
    current = repo()
    if current is None:
        return
    if st.session_state.pop("_reload_all", False):
        st.rerun()
    notice = st.session_state.pop("_local_notice", None)
    if notice:
        st.toast(notice[0], icon=notice[1])
    link = st.session_state.get("_link")
    outbox = None
    if link is not None:
        with current.lock:
            outbox = link.plan(current.path)
    _component(
        key=_KEY,
        data={
            "linked": link is not None, "name": link.name if link else "", "outbox": outbox,
            "skip": sorted(local_sync.SKIP_DIRS), "binary": sorted(local_sync.BINARY_EXTENSIONS),
            "max_file": settings.max_file_bytes, "max_files": local_sync.MAX_FILES, "max_total": local_sync.MAX_TOTAL_BYTES,
        },
        on_opened_change=_on_opened, on_linked_change=_on_linked, on_synced_change=_on_synced, on_stopped_change=_on_stopped,
    )


@st.fragment
def _idle() -> None:
    _panel()


@st.fragment(run_every=2)
def _syncing() -> None:
    _panel()


def render_local_folder() -> None:
    """Buttons (or the sync status) for the title bar. While a folder is linked this re-checks the workspace every 2 seconds."""
    if not available():
        return
    (_syncing if st.session_state.get("_link") is not None else _idle)()
