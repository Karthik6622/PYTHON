# RK Studio

A repository-aware AI coding IDE built entirely in Python with Streamlit. It uses NVIDIA Nemotron models through the OpenAI-compatible API (`https://integrate.api.nvidia.com/v1`, key in `NVIDIA_API_KEY`).

## Models

Pick the model in the agent panel; the choice applies to ASK, PLAN and AGENT runs.

In the dropdown order (best for coding and agent edits first):

- `nvidia/nemotron-3-ultra-550b-a55b` (default)
- `deepseek-ai/deepseek-v4.1-flash`
- `minimaxai/minimax-m3.1-flash`
- `poolside/laguna-xs-2.1`
- `nvidia/nemotron-3.5-super-vl-120b-a12b`
- `nvidia/nemotron-3.5-lightning-30b-a3b`
- `meta/muse-glimmer-30b`

Add more with `NVIDIA_MODELS=org/model-a,org/model-b`. Only text is sent; the VL model is used as a text model.

## Run

```powershell
pip install -r requirements.txt
copy .env.example .env     # fill in NVIDIA_API_KEY and GITHUB_TOKEN (or enter them in Settings)
streamlit run app.py
```

## Layout

The UI is a full-viewport, dark glass/neon shell modelled on VS Code (no page scroll).

- Title bar: brand, repository, branch picker, GitHub connect and Settings.
- Activity bar: switches the sidebar between Explorer, Search and Source Control.
- Sidebar: Explorer (open, create, rename, delete, refresh), Search, Source Control (stage, commit, push, discard).
- Centre: tabbed Ace editor with Save/Revert, plus TERMINAL, PROBLEMS, OUTPUT, TESTS and GIT DIFF tabs.
- Right: AI panel with a model picker, ASK / PLAN / AGENT modes, a live activity timeline (every read, edit, command and validation step), a review card and command approvals.
- Status bar: branch, changes, lint problems, and model / GitHub connection indicators.
- Drag the thin handles between the explorer, editor and agent panels (and above the terminal) to resize; use the arrows to collapse or widen a panel, double-click to reset. Sizes are remembered.
- The terminal opens in the repository folder and shows its full path in the prompt. A cloned repository lives under `workspaces/` (the connect dialog shows the exact location).

Flow: the agent edits files, then the review card shows each diff. Keep or Revert per file or for everything. Edits are applied first and reverted on request. Optionally commit, optionally push. Nothing is pushed automatically.

## Safety

- All file access is sandboxed to the repository folder.
- Terminal commands pass a policy check; risky ones need approval.
- Secrets are redacted from logs and agent output.
- `.env` and `workspaces/` are git-ignored.

## Working without a repository, and cloning

- A new window starts in a plain "local folder" (`workspaces/scratch`, or `SCRATCH_PATH`). Create and run files there with the editor, the agent and the terminal; no repository is needed. On a computer, the first time you create a file (or start the agent in AGENT mode) the operating system's folder window opens so you choose where files are saved; "Choose working folder" in the Explorer changes it later.
- "Connect a repository" asks for the repository, then "Clone and open" opens the operating system's folder dialog. The repository is saved in the folder you pick and opens in a new browser tab, so it never mixes with the files in the window you came from. Set `NATIVE_FOLDER_DIALOG=0` to skip the dialog.
- Every browser tab keeps its own folder (the `?w=` id in the address). Reloading a tab reopens its folder.
- Running on Streamlit Cloud: the server cannot open a window on your PC, but your browser can (Chrome, Edge or Opera). The Explorer shows one **Connect Local folder** button: pick a folder on your computer, then create, edit and run files in it. The text files are read into a working copy on the server, and every file created, edited, renamed or deleted afterwards (editor, agent or terminal) is written back to your folder within a couple of seconds (`Synced with ...`). Nothing can be created or run until a folder is open, and the terminal prompt shows the folder name. **Clone and open** in *Connect a repository* asks for a folder the same way and stores the repository there; it opens in the current window when that window is empty, otherwise in a new tab. Left out of the sync: `.git` (git commands run against the server's clone), tool folders (`node_modules`, `.venv`, ...), secrets (`.env`, keys), and, when opening a folder, binary files and files over 1 MB; at most 3000 files / 25 MB. After a reload, or in a new tab, the browser may ask for permission again: click **Reconnect <folder>** once. The server copy is lost when the app restarts, so the folder on your computer is the real copy.
- Terminal: the first `pip`/`python`/`playwright` command creates `.venv` in the folder, so installs stay in that folder; Playwright browsers go to `.playwright-browsers`. Both are kept out of `git status`. Playwright runs headless only, and `input()` prompts are not supported. On Streamlit Cloud, Playwright's system libraries must be listed in `packages.txt`.
- `TERMINAL_TIMEOUT_SECONDS` sets the command timeout (default 1800).

## Several people at once, and memory

- Every browser window is its own workspace, named by the `?w=` id in the address. On a shared deployment a visitor opening the bare address always gets a new workspace (own scratch folder, own keys, own undo list); bookmark the address to come back to it. Nobody sees another visitor's files or tokens. The terminal runs as the same operating-system user, so it is not a security sandbox between people who do not trust each other.
- GitHub: the account button in the top bar opens *Connect GitHub* (also once automatically). With `GITHUB_CLIENT_ID` set (an OAuth App with Device Flow) visitors click **Sign in with GitHub**, type a code on github.com and approve; otherwise they paste their own token. The token is kept in server memory for that window only and is used by Source Control, cloning and `git push` in the terminal. A `GITHUB_TOKEN` secret is ignored on a shared deployment unless `ALLOW_SHARED_GITHUB_TOKEN=1`.
- Chat memory: the conversation and the agent's memory of earlier requests are saved to `.studio_chats/` per window, so a refresh brings them back; an agent that is still running is reattached. Clearing the conversation deletes them.
- Large models: the agent waits up to `NVIDIA_TIMEOUT_SECONDS` (600) for a reply, asks again when a connection drops mid-reply, and continues with the next model (shown as a notice) if one keeps timing out. Set `NVIDIA_MODEL_FALLBACK=0` to disable the switch.
- Source Control shows the last commit with **Undo commit** (changes return to the staged list); terminal `git commit` / `git push` refresh it.

## Notes and limitations

- AGENT mode is inferred as the editing mode; the agent also has an extra `edit_file` tool.
- The Streamlit Cloud "Manage app" badge belongs to the host page; it is hidden on a best-effort basis (CSS plus a script) and may still show depending on the host.
- Not tested against live NVIDIA or GitHub services.
- The Ace editor component drops the first edit after it mounts (one typed character is not registered until the second). Avoid pressing Save right after a single keystroke.

## Tests

```powershell
python -m pytest tests -q
```
