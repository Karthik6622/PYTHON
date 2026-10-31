"""Open a folder from the visitor's own computer, and keep it in sync, when the app is hosted (Streamlit Cloud, a server).

A hosted app cannot show the operating system's folder window itself, but the visitor's browser can: it asks for a folder
(File System Access API: Chrome, Edge, Opera), reads the text files and sends them to the server, and later writes back every
file that was created or changed in the workspace. The server half is studio/services/local_sync.py.

One component serves two places: the "Open folder" button of the Explorer (role "explorer", always mounted in the side panel
because it also writes the changes back) and the "Clone and open" button of the connect dialog (role "clone")."""

from __future__ import annotations

import streamlit as st

from studio.config import settings
from studio.services import folders, local_sync
from studio.services.git_service import adopt_local_repository, parse_git_metadata
from studio.services.repository_service import RepositoryError

from .state import log, open_workspace, repo, repositories, window_id

_JS = r"""
const shared = (window.__rk = window.__rk || { handle: null, status: "", seen: new Set(), tried: "", reported: false });
const live = new Set();
const SENSITIVE = /^(\.env(\..+)?|.*\.(pem|key|p12|pfx)|id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|\.npmrc|\.pypirc|credentials(\.json)?)$/i;
const TEMPLATES = new Set([".env.example", ".env.sample", ".env.template", ".env.dist"]);
const supported = () => typeof window.showDirectoryPicker === "function";

function say(text) { shared.status = text; live.forEach((item) => item.draw()); }

function database() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("rk-studio", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("handles");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
async function remember(key, value) {
  const db = await database();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("handles", "readwrite");
    tx.objectStore("handles").put(value, key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}
async function recall(key) {
  try {
    const db = await database();
    return await new Promise((resolve, reject) => {
      const request = db.transaction("handles", "readonly").objectStore("handles").get(key);
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
    });
  } catch (error) { return null; }
}

async function pick() {
  try {
    return await window.showDirectoryPicker({ id: "rk-studio", mode: "readwrite" });
  } catch (error) {
    if (error && error.name !== "AbortError") say("Could not open the folder: " + (error.message || error));
    return null;
  }
}

async function isEmpty(dir) {
  for await (const _ of dir.values()) return false;
  return true;
}

// The branch and remote of a Git repository live in two small text files; the server rebuilds the repository from them.
// null means the folder has no .git folder at all. A missing or unreadable file is an empty text.
async function readGit(dir) {
  let git;
  try { git = await dir.getDirectoryHandle(".git"); } catch (error) { return null; }
  const found = { head: "", config: "" };
  for (const name of ["HEAD", "config"]) {
    try {
      const file = await (await git.getFileHandle(name)).getFile();
      if (file.size < 200000) found[name === "HEAD" ? "head" : "config"] = await file.text();
    } catch (error) { /* missing or unreadable */ }
  }
  return found;
}

// Every file and folder, breadth first: the files of the top folder come before anything nested, so a deep folder never
// pushes them out. Stops once there are far more files than the copy can hold; the rest is reported as not copied.
async function collect(root, cfg) {
  const found = [];
  const cap = cfg.max_files + cfg.list_limit;
  let level = [[root, ""]];
  while (level.length && found.length < cap) {
    const next = [];
    for (const [dir, prefix] of level) {
      for await (const [name, entry] of dir.entries()) {
        if (entry.kind === "directory") {
          if (!cfg.skip.includes(name)) next.push([entry, prefix + name + "/"]);
        } else {
          found.push({ path: prefix + name, name, entry });
        }
      }
    }
    level = next;
  }
  return found;
}

// Reads one file, or says why it is not copied. Nothing is dropped silently: a file that is left out is still listed.
async function readOne(item, cfg) {
  const file = await item.entry.getFile();
  const dot = item.name.lastIndexOf(".");
  const ext = dot > 0 ? item.name.slice(dot).toLowerCase() : "";
  if (cfg.binary.includes(ext)) return { size: file.size, why: "binary file (" + ext + ")" };
  if (SENSITIVE.test(item.name) && !TEMPLATES.has(item.name.toLowerCase())) return { size: file.size, why: "secret file" };
  if (file.size > cfg.max_file) return { size: file.size, why: "larger than " + Math.round(cfg.max_file / 1000) + " KB" };
  const text = await file.text();
  if (text.includes("\u0000") || text.includes("\ufffd")) return { size: file.size, why: "binary content" };
  return { size: file.size, text };
}

const READ_AT_ONCE = 8;

// Reads the files a few at a time (in order) until the copy is full. Files that do not fit are listed with the reason.
async function readAll(found, cfg) {
  const files = [];
  const listed = [];
  let bytes = 0;
  let left = 0;
  const full = () => files.length >= cfg.max_files || bytes >= cfg.max_total;
  const leave = (item, size, why) => {
    if (why.startsWith("left out")) left += 1;
    if (listed.length < cfg.list_limit) listed.push({ path: item.path, size: size || 0, why });
  };
  for (let start = 0; start < found.length; start += READ_AT_ONCE) {
    const group = found.slice(start, start + READ_AT_ONCE);
    say("Reading files " + Math.min(start + group.length, found.length) + " of " + found.length + " ...");
    const reads = await Promise.all(group.map((item) => (
      full() ? null : readOne(item, cfg).catch(() => ({ why: "could not be read" }))
    )));
    group.forEach((item, k) => {
      const result = reads[k];
      if (result === null) { leave(item, 0, "left out: the hosted copy is full"); return; }
      if (result.text === undefined) { leave(item, result.size, result.why); return; }
      if (full()) { leave(item, result.size, "left out: the hosted copy is full"); return; }
      files.push({ path: item.path, content: result.text });
      bytes += result.size;
    });
  }
  return { files, listed, left };
}

async function openFolder(self) {
  const chosen = await pick();
  if (!chosen) return;
  say("Scanning " + chosen.name + " ...");
  let read;
  let git;
  try {
    read = await readAll(await collect(chosen, self.cfg), self.cfg);
    git = await readGit(chosen);
  } catch (error) {
    say("Could not read the folder: " + (error.message || error));
    return;
  }
  try { await remember(self.cfg.window, chosen); } catch (error) { /* the folder still works for this page */ }
  shared.handle = chosen;
  shared.job = {
    id: Math.random().toString(36).slice(2) + Date.now().toString(36), name: chosen.name, files: read.files.length,
    groups: pieces(read.files), meta: { listed: read.listed, left: read.left, git }, sent: 0, acked: 0,
  };
  sendNext();
}

// The folder goes to the server in pieces of about 4 MB. The server confirms each piece before the next one is sent,
// so no single message is huge and nothing is dropped when the connection is slow.
const PIECE_CHARS = 4000000;

function pieces(files) {
  const groups = [];
  let group = [];
  let size = 0;
  for (const file of files) {
    if (group.length && size + file.content.length > PIECE_CHARS) { groups.push(group); group = []; size = 0; }
    group.push(file);
    size += file.content.length;
  }
  groups.push(group);
  return groups;
}

function sendNext() {
  const job = shared.job;
  if (!job || job.sent !== job.acked || job.sent >= job.groups.length) return;
  const index = job.sent;
  job.sent += 1;
  say("Sending " + job.files + " files (part " + job.sent + " of " + job.groups.length + ") ...");
  try {
    shared.api.setTriggerValue("chunk", {
      job: job.id, index, total: job.groups.length, name: job.name, files: job.groups[index],
      meta: index === 0 ? job.meta : null, nonce: Math.random(),
    });
  } catch (error) {
    shared.job = null;
    shared.handle = null;
    say("Could not send the folder: " + (error.message || error));
    return;
  }
  setTimeout(() => {
    if (shared.job === job && job.acked <= index) {
      shared.job = null;
      shared.handle = null;
      say("The server did not confirm the folder. Try again, or open a smaller folder.");
    }
  }, 180000);
}

// The server reports how many pieces it has received; the next piece goes out only after the previous one was confirmed.
function acknowledge(cfg) {
  const job = shared.job;
  const ack = cfg.ack;
  if (!job || !ack || ack.job !== job.id) return;
  job.acked = Math.max(job.acked, ack.count);
  if (job.acked >= job.groups.length) { shared.job = null; say(""); return; }
  sendNext();
}

async function reconnect(self) {
  const stored = await recall(self.cfg.window);
  if (stored) {
    try {
      if ((await stored.requestPermission({ mode: "readwrite" })) === "granted") {
        shared.handle = stored;
        say("");
        flushPending();
        return;
      }
    } catch (error) { /* fall through to the folder window */ }
  }
  const chosen = await pick();
  if (!chosen) return;
  if (chosen.name !== self.cfg.name) {
    if (!window.confirm("This window mirrors \"" + self.cfg.name + "\". Send its files to \"" + chosen.name + "\" instead?")) return;
    self.api.setTriggerValue("relinked", { name: chosen.name, nonce: Math.random() });
  }
  try { await remember(self.cfg.window, chosen); } catch (error) { /* ignore */ }
  shared.handle = chosen;
  say("");
  flushPending();
}

async function cloneAndOpen(self) {
  const field = (label) => document.querySelector('input[aria-label="' + label + '"]');
  const repository = ((field("Repository") || {}).value || "").trim();
  const branch = ((field("Branch (optional)") || {}).value || "").trim();
  if (repository.length < 3) { say("Enter the repository as owner/repo or paste its GitHub link."); return; }
  const chosen = await pick();
  if (!chosen) return;
  if (!(await isEmpty(chosen)) && !window.confirm("\"" + chosen.name + "\" is not empty. Files with the same names will be replaced by the repository's files. Continue?")) return;
  try { await remember(self.cfg.target, chosen); } catch (error) { say("Your browser would not keep access to the folder."); return; }
  if (self.cfg.target === self.cfg.window) shared.handle = chosen;
  say("Cloning into " + chosen.name + " ...");
  self.api.setTriggerValue("clone", { repo: repository, branch, name: chosen.name, nonce: Math.random() });
}

async function directory(parts, create) {
  let dir = shared.handle;
  for (const part of parts) dir = await dir.getDirectoryHandle(part, { create });
  return dir;
}

async function flush(self, batch) {
  const failed = [];
  say("Saving " + (batch.writes.length + batch.deletes.length) + " change(s) to " + self.cfg.name + " ...");
  for (const item of batch.writes) {
    try {
      const parts = item.path.split("/");
      const leaf = parts.pop();
      const file = await (await directory(parts, true)).getFileHandle(leaf, { create: true });
      const out = await file.createWritable();
      await out.write(item.base64 !== undefined ? Uint8Array.from(atob(item.base64), (c) => c.charCodeAt(0)) : item.content);
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
  say(failed.length ? failed.length + " file(s) could not be written. Check the folder permissions." : "All changes saved to " + self.cfg.name + ".");
  self.api.setTriggerValue("synced", { id: batch.id, failed, nonce: Math.random() });
}

function flushPending() {
  live.forEach((item) => {
    const batch = item.cfg.outbox;
    if (item.cfg.role === "explorer" && batch && shared.handle && !shared.seen.has(batch.id)) {
      shared.seen.add(batch.id);
      flush(item, batch);
    }
  });
}

async function restore(self) {
  if (shared.tried === self.cfg.window) return;
  shared.tried = self.cfg.window;
  const stored = await recall(self.cfg.window);
  try {
    if (stored && (await stored.queryPermission({ mode: "readwrite" })) === "granted") shared.handle = stored;
  } catch (error) { /* needs a click */ }
  live.forEach((item) => item.draw());
  flushPending();
}

export default function (component) {
  const host = component.parentElement;
  const cfg = component.data;
  let box = host.querySelector(".rk");
  if (!box) { box = document.createElement("div"); box.className = "rk"; host.appendChild(box); }
  const self = { api: component, cfg, box };

  const button = (label, onClick, primary) => {
    const item = document.createElement("button");
    item.type = "button";
    item.textContent = label;
    item.className = primary ? "primary" : "";
    item.onclick = onClick;
    return item;
  };
  const note = (text, extra) => {
    const item = document.createElement("span");
    item.className = "note" + (extra ? " " + extra : "");
    item.textContent = text;
    return item;
  };
  self.draw = () => {
    const parts = [];
    if (!cfg.visible) { box.replaceChildren(); return; }
    if (!supported()) {
      parts.push(note(cfg.role === "clone"
        ? "Saving a repository to your computer needs Chrome or Edge."
        : "Opening a folder from your computer needs Chrome or Edge. Files are kept on the server."));
    } else if (cfg.role === "clone") {
      parts.push(button("Clone and open", () => cloneAndOpen(self), true));
      if (shared.status) parts.push(note(shared.status));
    } else if (cfg.linked && shared.handle) {
      const label = document.createElement("span");
      label.className = "live";
      label.textContent = "Synced with " + cfg.name;
      label.title = "Changes made here are saved to this folder on your computer.";
      parts.push(label, button("Connect Local folder", () => openFolder(self), false));
    } else if (cfg.linked) {
      parts.push(button("Reconnect " + cfg.name, () => reconnect(self), true));
      if (shared.status) parts.push(note(shared.status));
    } else {
      parts.push(button("Connect Local folder", () => openFolder(self), true));
      if (shared.status) parts.push(note(shared.status));
    }
    box.replaceChildren(...parts);
  };

  live.add(self);
  if (cfg.role === "clone" && shared.opened !== cfg.opened) { shared.opened = cfg.opened; shared.status = ""; }
  self.draw();
  if (!shared.reported && cfg.role === "explorer") {
    shared.reported = true;
    component.setStateValue("picker", supported());
  }
  if (cfg.role === "explorer") {
    shared.api = component;
    acknowledge(cfg);
    if (cfg.linked) restore(self);
    flushPending();
  }
  return () => { live.delete(self); };
}
"""

_CSS = """
.rk { display:flex; align-items:center; gap:8px; flex-wrap:wrap; font:12.5px/1.2 "Segoe UI", system-ui, sans-serif; color:#dcfff0; min-height:36px; }
button { cursor:pointer; border:1px solid rgba(15,191,107,.55); background:rgba(15,191,107,.12); color:#dcfff0; border-radius:999px;
  padding:6px 14px; font:inherit; font-weight:600; white-space:nowrap; transition:background .15s, box-shadow .15s; }
button:hover { background:rgba(15,191,107,.3); box-shadow:0 0 12px rgba(15,191,107,.45); }
button.primary { background:linear-gradient(90deg,#2bff9a,#0fbf6b); border-color:transparent; color:#021a0e; }
.live { display:inline-flex; align-items:center; gap:7px; padding:6px 12px; border-radius:999px; border:1px solid rgba(52,211,153,.5); background:rgba(52,211,153,.1); color:#34d399; font-weight:600; white-space:nowrap; max-width:200px; overflow:hidden; text-overflow:ellipsis; }
.live::before { content:""; width:7px; height:7px; border-radius:50%; background:#34d399; box-shadow:0 0 8px #34d399; flex:none; }
.note { color:#6fa08a; }
"""

_component = None
try:
    _component = st.components.v2.component("rk_local_folder", js=_JS, css=_CSS)
except Exception:  # Streamlit older than components v2: only the operating system's folder window (local runs) is available
    _component = None

_KEY = "rk_local"
_CLONE_KEY = "rk_clone"


def available() -> bool:
    """The browser folder feature is for hosted deployments; on the user's own computer the operating system's dialog is used."""
    return _component is not None and not folders.native_picker_available()


def _event(key: str, name: str) -> dict:
    state = st.session_state.get(key)
    value = getattr(state, name, None) if state is not None else None
    if value is None and isinstance(state, dict):
        value = state.get(name)
    return value if isinstance(value, dict) else {}


def picker_supported() -> bool:
    """False only when the browser reported that it cannot open folders (anything but Chrome, Edge or Opera)."""
    state = st.session_state.get(_KEY)
    value = getattr(state, "picker", None) if state is not None else None
    if value is None and isinstance(state, dict):
        value = state.get("picker")
    return value is not False


def _notify(text: str, icon: str = ":material/info:") -> None:
    """Callbacks must not draw anything, so messages wait here until the panel runs."""
    log(text)
    st.session_state["_local_notice"] = (text, icon)


def _adopt_git(destination, meta: object) -> str:
    """When the folder on the user's computer is a Git repository, make the opened copy one too (same branch and remote).

    Returns a short sentence for the notice. GitHub sign-in is only requested here when GitHub really needs it (a private remote)."""
    if not isinstance(meta, dict):
        return " No .git folder was found in this folder, so Git features are off."
    branch, url = parse_git_metadata(meta.get("head"), meta.get("config"))
    # A detached HEAD is still a real repository. Keep Git/source control available even if the browser
    # metadata cannot identify its checked-out branch; use the conventional local branch as a safe fallback.
    branch_known = bool(branch)
    branch = branch or "main"
    outcome = adopt_local_repository(destination, branch, url)
    if outcome["needs_login"] and not settings.github_token:
        st.session_state["_ask_github"] = True
        return f" Git branch {branch}. Connect GitHub to access the remote."
    if not branch_known:
        return f" Git repository detected; branch name unavailable, so the hosted copy uses {branch}."
    return f" Git branch {branch}."


_IMPORT_KEY = "_local_import"  # the folder that is arriving piece by piece
_ACK_KEY = "_local_ack"  # how many pieces of which folder the server has received so far


def _on_chunk() -> None:
    """One piece of the folder from the browser. The browser sends the next piece only after this acknowledgement.

    Callbacks must stay light: pieces are only stored here; the last piece triggers the import."""
    event = _event(_KEY, "chunk")
    job, index, total = event.get("job"), event.get("index"), event.get("total")
    if not isinstance(job, str) or not isinstance(index, int) or not isinstance(total, int) or total < 1:
        return
    pending = st.session_state.get(_IMPORT_KEY)
    if index == 0 or not isinstance(pending, dict) or pending.get("job") != job:
        meta = event.get("meta")
        pending = {
            "job": job, "name": local_sync.clean_name(event.get("name")), "files": [], "count": 0,
            "meta": meta if isinstance(meta, dict) else {},
        }
        st.session_state[_IMPORT_KEY] = pending
    if index != pending["count"]:
        return  # out of order or repeated: no acknowledgement, so the browser waits and then reports the problem
    piece = event.get("files")
    if isinstance(piece, list):
        pending["files"].extend(piece)
    pending["count"] = index + 1
    if pending["count"] < total:
        st.session_state[_ACK_KEY] = {"job": job, "count": pending["count"]}
        return
    st.session_state.pop(_IMPORT_KEY, None)
    st.session_state[_ACK_KEY] = {"job": job, "count": total}
    _finish(pending)


def _finish(pending: dict) -> None:
    """Writes the received folder into this window's workspace and opens it."""
    name = pending["name"]
    meta = pending.get("meta") or {}
    destination = (settings.workspace_path / "local" / window_id() / name).resolve()
    listed = local_sync.clean_listing(meta.get("listed"))
    browser_left = meta.get("left") if isinstance(meta.get("left"), int) else 0
    try:
        result = local_sync.import_files(destination, pending["files"])
        location = local_sync.clean_location(local_sync.load_sidecar(destination).get("location"))
        local_sync.update_sidecar(destination, listed=listed)
        git_note = _adopt_git(destination, meta.get("git"))
        folder = repositories.open_scratch(str(destination))
    except (local_sync.SyncError, RepositoryError) as exc:
        _notify(getattr(exc, "message", None) or str(exc), ":material/error:")
        return
    except Exception as exc:  # report the failure instead of leaving the page stuck on "Sending files"
        _notify(f"Could not open {name}: {exc.__class__.__name__}. Try again, or open a smaller folder.", ":material/error:")
        return
    open_workspace(folder, local_sync.LocalLink(
        name, known=local_sync.snapshot(destination), location=location, listed=listed,
    ))
    st.session_state["_reload_all"] = True
    left = browser_left + result.left_out
    extra = ""
    if listed:
        extra += f" {len(listed)} file(s) are shown in the explorer but not copied; each one shows its reason."
    if left:
        extra += (
            f" The hosted copy holds {local_sync.MAX_TOTAL_BYTES // 1_000_000} MB of text, so {left} file(s) were left out. "
            "Run the Studio on your computer to open the whole folder."
        )
    _notify(f"Opened {name}: {result.count} files.{git_note}{extra}", ":material/folder_open:")


def _on_relinked() -> None:
    event = _event(_KEY, "relinked")
    link = st.session_state.get("_link")
    current = repo()
    if link is None or current is None:
        return
    link.name = local_sync.clean_name(event.get("name"))
    link.known, link.pending, link.fresh = {}, None, True
    repositories.remember(window_id(), current.path, current.github, current.scratch, link.name, True)


def _on_synced() -> None:
    event = _event(_KEY, "synced")
    link = st.session_state.get("_link")
    if link is not None:
        link.acknowledge(event.get("id"))
    failed = event.get("failed")
    if failed:
        _notify(f"{len(failed)} file(s) could not be saved to your folder.", ":material/error:")


def _on_clone() -> None:
    st.session_state["_clone_job"] = _event(_CLONE_KEY, "clone")


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
        if outbox is None and link.fresh:  # the whole workspace has reached the user's folder
            link.fresh = False
            repositories.mark_synced(window_id())
    _component(
        key=_KEY,
        data={
            "role": "explorer", "window": window_id(), "visible": bool(st.session_state.get("_local_visible", True)),
            "linked": link is not None, "name": link.name if link else "", "outbox": outbox,
            "ack": st.session_state.get(_ACK_KEY),
            "skip": sorted(local_sync.SKIP_DIRS), "binary": sorted(local_sync.BINARY_EXTENSIONS),
            "max_file": settings.max_file_bytes, "max_files": local_sync.MAX_FILES, "max_total": local_sync.MAX_TOTAL_BYTES,
            "list_limit": local_sync.LISTED_LIMIT,
        },
        on_chunk_change=_on_chunk, on_relinked_change=_on_relinked, on_synced_change=_on_synced,
    )


@st.fragment
def _idle() -> None:
    _panel()


@st.fragment(run_every=2)
def _syncing() -> None:
    _panel()


def render_local_folder() -> None:
    """The Open folder button (or the sync status) of the Explorer. While a folder is linked this re-checks the workspace every 2 seconds."""
    if not available():
        return
    (_syncing if st.session_state.get("_link") is not None else _idle)()


def render_clone_button(target_window: str, opened: str) -> None:
    """Clone and open: asks for a folder in the browser, then the server clones into it. `target_window` receives the result."""
    if not available():
        return
    _component(
        key=_CLONE_KEY,
        data={"role": "clone", "window": window_id(), "target": target_window, "opened": opened, "visible": True},
        on_clone_change=_on_clone,
    )
