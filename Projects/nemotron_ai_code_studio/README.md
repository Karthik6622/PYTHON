# RK Studio

A repository-aware AI coding IDE built entirely in Python with Streamlit. It uses NVIDIA Nemotron models through the OpenAI-compatible API (`https://integrate.api.nvidia.com/v1`, key in `NVIDIA_API_KEY`).

## Models

Pick the model in the agent panel; the choice applies to ASK, PLAN and AGENT runs.

- `nvidia/nemotron-3-ultra-550b-a55b` (default)
- `nvidia/nemotron-3.5-super-vl-120b-a12b`
- `nvidia/nemotron-3.5-lightning-30b-a3b`

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

- A new window starts in a plain "local folder" (`workspaces/scratch`, or `SCRATCH_PATH`). Create and run files there with the editor, the agent and the terminal; no repository is needed. On a computer, "Choose working folder" in the Explorer switches to any folder.
- "Connect a repository" asks for the repository, then "Clone and open" opens the operating system's folder dialog. The repository is saved in the folder you pick and opens in a new browser tab, so it never mixes with the files in the window you came from. Set `NATIVE_FOLDER_DIALOG=0` to skip the dialog.
- Every browser tab keeps its own folder (the `?w=` id in the address). Reloading a tab reopens its folder.
- Running on Streamlit Cloud: the server cannot open a window on your PC or write to its disk, so repositories are saved on the server and are lost when the app restarts. Run RK Studio on your own computer to keep files there.
- Terminal: the first `pip`/`python`/`playwright` command creates `.venv` in the folder, so installs stay in that folder; Playwright browsers go to `.playwright-browsers`. Both are kept out of `git status`. Playwright runs headless only, and `input()` prompts are not supported. On Streamlit Cloud, Playwright's system libraries must be listed in `packages.txt`.
- `TERMINAL_TIMEOUT_SECONDS` sets the command timeout (default 1800).

## Notes and limitations

- AGENT mode is inferred as the editing mode; the agent also has an extra `edit_file` tool.
- The Streamlit Cloud "Manage app" badge belongs to the host page; it is hidden on a best-effort basis (CSS plus a script) and may still show depending on the host.
- Not tested against live NVIDIA or GitHub services.
- The Ace editor component drops the first edit after it mounts (one typed character is not registered until the second). Avoid pressing Save right after a single keystroke.

## Tests

```powershell
python -m pytest tests -q
```
