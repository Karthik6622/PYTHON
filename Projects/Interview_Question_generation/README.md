# Interview Studio

A Streamlit chat-style interviewer workspace with a **futuristic/cyberpunk theme** and **red color palette**. Save a resume and job description, choose the question count (3-30), complexity level (Low/Medium/High), and coding toggle, then generate enterprise-level interview guides with Nemotron. Questions are project-based, scenario-driven, and reference specific facts from the candidate's resume.

## Features

- **Cyberpunk UI**: Dark futuristic theme with red accent colors, animated backgrounds, and glow effects
- **Question Count**: 3-30 questions via slider
- **Complexity Levels**: Low (foundational), Medium (practical application), High (strategic/system mastery)
- **Coding Questions**: Optional ~15% coding questions based on resume tech stack
- **Project-Based Questions**: Every question references specific resume facts (companies, projects, technologies, metrics)
- **Enterprise Quality**: Probes system design, scalability, reliability, security, team impact, business value
- **Nemotron Optimized**: Prompts engineered for NVIDIA Nemotron 3.5 Bolt for high-quality output

## Run on Windows

Install Python 3.10 or newer. Open this folder in VS Code, then run in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py -m streamlit run project.py
```

Open the local URL Streamlit prints, usually http://localhost:8501. Keep the terminal open while using the app. If PowerShell blocks activation, skip that command and run the remaining commands.

## NVIDIA API Key

Add `NVIDIA_API_KEY = "..."` to `.streamlit/secrets.toml`. The app connects to `https://integrate.api.nvidia.com/v1` and uses `nvidia/nemotron-3.5-bolt-e4b` through the OpenAI-compatible chat completions API.

## Chat History and Privacy

Each browser tab has its own Streamlit session, so new tabs and devices start with a fresh workspace. Chats and extracted resume/job-description text are held in that session's memory, are not written to a shared history file, and clear when the tab is refreshed or closed. The app does not synchronize tab or device data. `.streamlit/secrets.toml` is ignored by Git.

Resume and job-description text are sent to NVIDIA when generating a guide or answering a follow-up. Don't use this app to process candidate data unless your NVIDIA service configuration and organization policies allow it.

## Usage

1. **Upload Resume** (required) and **Job Description** (required) as PDF, DOCX, or TXT files
2. **Configure Settings** in sidebar:
   - Number of questions: 3-30
   - Complexity: Low / Medium / High
   - Include coding questions: toggle
3. **Generate First Guide** - creates structured interview guide with:
   - Project/experience questions tied to resume facts
   - Coding questions based on resume tech stack (if enabled)
   - Practical scenario questions
   - "What to look for" evaluation table
   - Suggested interview approach
4. **Follow-up Chat** - ask for more questions, explanations, or modifications
