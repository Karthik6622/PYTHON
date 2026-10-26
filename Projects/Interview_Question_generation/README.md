# Interview Studio

A Streamlit web app that creates interview questions tailored to the candidate's demonstrated experience and a job description. Supports resume and job-description uploads in PDF, DOCX, or TXT format, plus pasted job-description text. Files are processed in memory and are not saved by the app.

## Run on Windows with PowerShell

Install Python 3.10 or newer if it is not already installed. In VS Code, open this folder and select **Terminal → New Terminal**. Run these commands one at a time:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
$env:HF_TOKEN="your Hugging Face access token"
py -m streamlit run kk.py
```

Streamlit will print a local URL, usually http://localhost:8501. Open it in your browser. Keep the terminal open while the app is running. If PowerShell blocks activation, you can skip the activation command and run `py -m pip install -r requirements.txt` and `py -m streamlit run kk.py` directly.

## Hugging Face token

Set `HF_TOKEN` in the same PowerShell terminal before launching Streamlit. Do not paste the token into the Python source or commit it to Git. If the token was posted in a shared place, revoke it and create a replacement in Hugging Face settings.

The app calls `deepseek-ai/DeepSeek-V4.1-Flash:novita` through `https://router.huggingface.co/v1`. The first generation request requires a valid token and access to the selected model.

## Deploy on Vercel

Vercel is designed primarily for serverless web frameworks and does not provide a standard one-click deployment path for a persistent Streamlit server. Run this app locally using the steps above, or deploy it to a Python-friendly hosting service that supports Streamlit. If you need a Vercel-hosted version, use the Next.js app variant instead of this Streamlit project.

Scanned PDFs without selectable/extractable text need OCR before upload. Each file is limited to 5 MB.
