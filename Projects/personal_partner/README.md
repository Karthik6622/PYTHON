# KindSpace Personal Assistant

KindSpace is a Streamlit personal AI assistant with local accounts and private, per-user conversation history. It uses an OpenAI-compatible streaming API and supports NVIDIA-hosted models through configuration. It is an AI assistant, not a human, romantic partner, therapist, doctor, or emergency service.

## Requirements

- Python 3.11 or newer
- An API key for an OpenAI-compatible chat completion service

## Run locally

```powershell
cd Projects\personal_partner
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `NVIDIA_API_KEY` in `.env` or `.streamlit/secrets.toml`. The default model is `nvidia/nemotron-3.5-bolt-e4b`, matching Interview Studio. You can override it with `LLM_MODEL` or `NVIDIA_MODEL`; `LLM_BASE_URL` defaults to NVIDIA's OpenAI-compatible endpoint. Generic `LLM_API_KEY` remains supported. Secrets take precedence over environment variables. Never commit real keys.

Start the app:

```powershell
py -m streamlit run app.py
```

The project uses the provider's OpenAI-compatible `/chat/completions` endpoint, streams replies, and uses the same Nemotron thinking-off request variants as Interview Studio. Temperature must be from 0 to 1, and max tokens from 64 to 4000.

## Google and GitHub sign-up

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`. Create a Google OAuth client and a GitHub OAuth App, then replace their example credentials. For local development, use `http://localhost:8501/oauth2callback` as Google's authorized redirect URI and `http://localhost:8501` as GitHub's callback URL. Set both callback URLs to your deployed app's absolute URL when hosting it elsewhere. Google uses Streamlit's OIDC login; GitHub uses OAuth authorization code flow. Both providers must return a verified email. Social identities are linked to an existing local account only when the verified email matches.

## Forgot password and account security

The log in page links to a password reset page. Enter the account email; if no account exists you get "No account exists with that email", otherwise you choose a new password on the same page. No email is sent and passwords are never shown (they are stored only as bcrypt hashes). Accounts lock for 15 minutes after 5 failed passwords; a successful reset clears the lock. Sign-in, lockout, and reset events are written to the `kindspace.audit` log (no passwords or tokens).

## Run tests

```powershell
py -m pytest
```

## Storage and privacy

Account records are stored in `data/users.json`. Each account's conversations are stored separately in `data/conversations/{user_id}.json`, where `user_id` is a random UUID. Passwords are bcrypt hashes; API keys are never written to JSON. JSON changes use file locks and atomic replacement. Malformed JSON is copied to a timestamped backup before a clean file is created. Local account and conversation files are ignored by Git.

This app is designed for a trusted local machine or a properly secured private deployment. Anyone with filesystem access to the server can access local data. Conversation messages and selected preferences are sent to the configured model provider; account passwords, password hashes, email addresses, and internal file paths are not included. Review your provider's data handling terms before using sensitive information.

The Google and GitHub client secrets and Streamlit cookie secret must remain private. If a credential has been added to an example file or source control, revoke it with the provider and create a new one.

## Browser and device support

The interface uses responsive Streamlit layouts, system fonts, high-contrast colors, keyboard focus indicators, and reduced-motion preferences. It adapts to narrow phone screens and wider tablet/desktop views without relying on remote fonts or browser-specific layout features. Test the deployed app on the browsers and devices your users rely on.
