# Interview Studio

A Streamlit chat-style interviewer workspace. Save a resume and job description, choose the question count and coding toggle, then generate the first guide with one button. After it appears, use chat to ask about a question or request targeted follow-ups. Chats and candidate context are kept only in the current Streamlit browser session.

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

Each browser tab has its own Streamlit session, so new tabs and devices start with a fresh workspace. Chats and extracted resume/job-description text are held in that session's memory, are not written to a shared history file, and clear when the tab is refreshed or closed. The app does not synchronize tab or device data. `.streamlit/secrets.toml` is ignored by Git.

Resume and job-description text are sent to NVIDIA when generating a guide or answering a follow-up. Don't use this app to process candidate data unless your NVIDIA service configuration and organization policies allow it.

Coding mode uses exactly a 90:10 split: choose 10 or 20 total questions to get one or two coding questions. Coding language is taken from the resume where available. Every main question requests 4–6 concise follow-up probes, aiming for four. NVIDIA requests stream output as it arrives, turn off model reasoning for this straightforward generation task, use a 300-second timeout with automatic retries disabled, and cap output at 2,500 tokens. Resume and job-description text are each limited to 12,000 characters to keep requests smaller. The app records total response time. Scanned PDFs without extractable text need OCR before upload. Each file is limited to 5 MB.
