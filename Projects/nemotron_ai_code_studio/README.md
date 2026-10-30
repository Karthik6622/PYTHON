# Nemotron AI Code Studio

A repository-aware AI coding IDE built entirely in Python with Streamlit. It uses NVIDIA `nvidia/nemotron-3-ultra-550b-a55b` through the OpenAI-compatible API.

## Run

```powershell
pip install -r requirements.txt
copy .env.example .env     # fill in NVIDIA_API_KEY and GITHUB_TOKEN (or enter them in Settings)
streamlit run app.py
```

## Layout

- Top bar: repository, branch, status, Settings, GitHub.
- Left: Explorer (open, create, rename, delete, refresh), Search, Source Control (stage, commit, push, discard).
- Centre: tabbed Ace editor with Save/Revert, plus TERMINAL, PROBLEMS, OUTPUT, TESTS and GIT DIFF tabs.
- Right: AI panel with ASK / PLAN / AGENT modes, files inspected, proposed changes (Review, Apply, Reject) and command approvals.

Flow: AI proposes changes, you review, you accept, optionally commit, optionally push. Nothing is pushed automatically.

## Safety

- All file access is sandboxed to the repository folder.
- Terminal commands pass a policy check; risky ones need approval.
- Secrets are redacted from logs and agent output.
- `.env` and `workspaces/` are git-ignored.

## Notes and limitations

- AGENT mode is inferred as the editing mode; the agent also has an extra `edit_file` tool.
- Not tested against live NVIDIA or GitHub services.
- The Ace editor component drops the first edit after it mounts (one typed character is not registered until the second). Avoid pressing Save right after a single keystroke.

## Tests

```powershell
python -m pytest tests -q
```
