# Interview Studio

A Streamlit web app that creates interview questions tailored to a candidate's demonstrated experience and a job description. It accepts PDF, DOCX, and TXT files, or pasted job-description text. Uploaded files are processed in memory and are not saved by the app.

## Run on Windows

Install Python 3.10 or newer. Open this folder in VS Code, then open **Terminal → New Terminal** and run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py -m streamlit run project.py
```

Open the local URL Streamlit prints, usually http://localhost:8501. Keep the terminal open while the app is running. If PowerShell blocks activation, skip the activation line and run the remaining commands.

## Deployment

Vercel does not provide a standard deployment workflow for a persistent Streamlit app. Use a Python and Streamlit compatible host. Streamlit Community Cloud deploys apps from GitHub; see the [deployment guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy).

Scanned PDFs without extractable text need OCR before upload. Each file is limited to 5 MB.
