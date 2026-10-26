# Interview Question Generation

A Streamlit application that generates interview questions based on a candidate's resume, experience, and job description using an LLM.

## Project Structure

```text
Interview_Question_generation/
├── .gitignore
├── project.py
├── README.md
└── requirements.txt
```

## Prerequisites

- Python 3.10 or later
- PowerShell
- Internet connection
- Hugging Face access token

## First-Time Setup

Open the `Interview_Question_generation` folder in VS Code.

Open:

**Terminal → New Terminal**

Make sure you are using PowerShell.

Run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
```

If PowerShell blocks virtual-environment activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Configure Hugging Face Token

The application requires a Hugging Face access token.

Set the token in the same PowerShell terminal before starting Streamlit:

```powershell
$env:HF_TOKEN="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"
```

Replace `YOUR_HUGGING_FACE_TOKEN_HERE` with your actual Hugging Face token.

Verify that the token is available:

```powershell
if ($env:HF_TOKEN) { "HF_TOKEN is set" } else { "HF_TOKEN is missing" }
```

Expected result:

```text
HF_TOKEN is set
```

Never add the real Hugging Face token to `README.md`, `project.py`, or Git.

## Run the Application

```powershell
py -m streamlit run project.py
```

Streamlit will display the local application address in the terminal.

The default is normally:

```text
http://localhost:8501
```

Keep the terminal running while using the application.

Press:

```text
Ctrl + C
```

to stop the application.

## Quick Start

For a fresh setup:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
$env:HF_TOKEN="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"
py -m streamlit run project.py
```

For subsequent runs:

```powershell
.\.venv\Scripts\Activate.ps1
$env:HF_TOKEN="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"
py -m streamlit run project.py
```

IMPORTANT: `$env:HF_TOKEN` is set only for the current PowerShell session. If you close PowerShell, set the token again before starting the application.

## Troubleshooting

### HF_TOKEN is missing

Run:

```powershell
$env:HF_TOKEN="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"
```

Verify:

```powershell
if ($env:HF_TOKEN) { "HF_TOKEN is set" } else { "HF_TOKEN is missing" }
```

Then:

```powershell
py -m streamlit run project.py
```

### Virtual Environment Activation Is Blocked

Run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Streamlit Is Not Found

Install the requirements:

```powershell
py -m pip install -r requirements.txt
```

Then:

```powershell
py -m streamlit run project.py
```

## Git Security

Do not commit secrets or your local virtual environment.

Ensure `.gitignore` contains:

```gitignore
.venv/
.env
__pycache__/
*.pyc
```

Never commit your actual*Hugging Face access token.

If a t*ken is accidentally pushed to Git *r shared publicly, revoke it and g*nerate a new token.

