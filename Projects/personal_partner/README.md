# KindSpace Personal Assistant

KindSpace is a Streamlit personal AI assistant with local accounts and private, per-user conversation history. It uses an OpenAI-compatible streaming API and supports NVIDIA-hosted models through configuration. It is an AI assistant, not a human, romantic partner, therapist, doctor, or emergency service.

## Requirements

- Python 3.11 or newer
- An API key for an OpenAI-compatible chat completion service

## Run locally

```powershell
cd "personal partner"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL` in `.env`, or copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and set the values there. Secrets take precedence over environment variables. Never commit a real key.

Start the app:

```powershell
py -m streamlit run app.py
```

The project uses the provider's OpenAI-compatible `/chat/completions` endpoint. `LLM_BASE_URL` should be the API base URL (for NVIDIA, `https://integrate.api.nvidia.com/v1`); `LLM_MODEL` must be a model available to your API key. Temperature must be from 0 to 1, and max tokens from 64 to 4000.

## Run tests

```powershell
py -m pytest
```

## Storage and privacy

Account records are stored in `data/users.json`. Each account's conversations are stored separately in `data/conversations/{user_id}.json`, where `user_id` is a random UUID. Passwords are bcrypt hashes; API keys are never written to JSON. JSON changes use file locks and atomic replacement. Malformed JSON is copied to a timestamped backup before a clean file is created. Local account and conversation files are ignored by Git.

This app is designed for a trusted local machine or a properly secured private deployment. Anyone with filesystem access to the server can access local data. Conversation messages and selected preferences are sent to the configured model provider; account passwords, password hashes, email addresses, and internal file paths are not included. Review your provider's data handling terms before using sensitive information.

## Browser and device support

The interface uses responsive Streamlit layouts, system fonts, high-contrast colors, keyboard focus indicators, and reduced-motion preferences. It adapts to narrow phone screens and wider tablet/desktop views without relying on remote fonts or browser-specific layout features. Test the deployed app on the browsers and devices your users rely on.
