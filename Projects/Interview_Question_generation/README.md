# Interview Studio

A Streamlit interviewer workspace that builds experience-level interview guides from a candidate resume and a job description. It supports PDF, DOCX, and TXT uploads, editable guides, separate interview sessions, and a session history of generated sets and edits.

When coding questions are enabled, choose 10 or 20 total questions to keep the mix at exactly 90% project/experience questions and 10% coding questions. Coding challenges use a programming language explicitly identified in the resume where possible.

## Run on Windows

Install Python 3.10 or newer. Open this folder in VS Code, then run in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py -m streamlit run project.py
```

Open the local URL Streamlit prints, usually http://localhost:8501. Keep the terminal open while using the app. If PowerShell blocks activation, skip that command and run the remaining commands.

## Groq API key

Add your key to `.streamlit/secrets.toml` as `GROQ_API_KEY = "..."`. This file is ignored by Git. The app calls Groq's OpenAI-compatible Responses API with `openai/gpt-oss-20b`.

## Sessions and privacy

Each interview session keeps its resume text, job description, guides, and history in Streamlit's in-memory session state. Separate sessions do not share context. This data is not written to disk; closing or refreshing the browser session or restarting the app clears it. Uploaded documents are sent to Groq only when generating a guide.

Vercel does not provide a standard deployment workflow for a persistent Streamlit app. For hosting, use a Python and Streamlit compatible service. Streamlit Community Cloud deploys apps from GitHub; see its [deployment guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy).

Scanned PDFs without extractable text need OCR before upload. Each file is limited to 5 MB.
