# Interview Studio

A Streamlit chat-style interviewer workspace. It creates experience-level questions from a resume and job description, supports optional coding questions, and saves named interview chats with their context and generated question history in one local JSON file.

## Run on Windows

Install Python 3.10 or newer. Open this folder in VS Code, then run in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py -m streamlit run project.py
```

Open the local URL Streamlit prints, usually http://localhost:8501. Keep the terminal open while using the app. If PowerShell blocks activation, skip that command and run the remaining commands.

## NVIDIA API key

Add `NVIDIA_API_KEY = "..."` to `.streamlit/secrets.toml`. The app connects to `https://integrate.api.nvidia.com/v1` and uses `deepseek-ai/deepseek-v4.1-flash` through the OpenAI-compatible chat completions API.

## Chat history and privacy

Chats, question history, session titles, and extracted resume/job-description text are saved in `interview_sessions.json` beside `project.py`. The app reads this file at startup and writes changes atomically. Both `interview_sessions.json` and `.streamlit/secrets.toml` are ignored by Git; keep backups private and delete the JSON file to clear saved chats.

This local JSON store is intended for a private, single-user app instance. It has no sign-in or per-user access control, so anyone who can access a shared deployment could see its saved interviews. Use an authenticated database-backed setup before exposing the app to multiple users. Uploaded documents are sent to NVIDIA only when a guide is generated.

Coding mode uses exactly a 90:10 split: choose 10 or 20 total questions to get one or two coding questions. Coding language is taken from the resume where available. Scanned PDFs without extractable text need OCR before upload. Each file is limited to 5 MB.
