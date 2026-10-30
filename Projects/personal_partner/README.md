# WithYou (Personal Partner)

WithYou is a Streamlit personal AI companion with local accounts and private, per-user conversation history. It uses an OpenAI-compatible streaming API and supports NVIDIA-hosted models through configuration. It is an AI assistant, not a human, therapist, doctor, or emergency service.

## Features

- Friendly, casual replies. Pick topics in Settings or use the chat toggle; the **Romantic** topic switches to a warm, affectionate (PG-13) tone while still being an AI.
- Today's date and time come from the browser timezone (UTC fallback). Weather questions use the free Open-Meteo API; set an optional **Your city** in Settings so the assistant knows where you are.

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

Set `NVIDIA_API_KEY` and `TAVILY_API_KEY` in `.env` or `.streamlit/secrets.toml`.

For pictures in chat ("generate an image of ..."), set `AI_HORDE_API_KEY` (the same AI Horde FLUX.1 schnell setup AI Book Studio uses). It is a free shared queue, so a picture can take from a few seconds to a few minutes.

For voice chat also set `GROQ_API_KEY`. Speech is transcribed by NVIDIA `nemotron-3-nano-omni-30b-a3b-reasoning` (using the same `NVIDIA_API_KEY`), with Groq `whisper-large-v3` as a fallback. The Nemotron chat model writes the reply, and Groq text-to-speech reads it aloud.

### How questions are routed

```
User -> NVIDIA Nemotron decides (src/router.py) -> needs live web info?
  NO:  NVIDIA Nemotron -> answer
  YES: Tavily search (src/web_search.py) with the query Nemotron wrote -> current web results -> NVIDIA Nemotron -> answer
```

There is no fixed keyword classifier. Nemotron reads the recent conversation and decides whether it can answer from its own knowledge or needs a live search. When it needs one, it also writes the search query, so follow-ups such as "and before him?" are searched in context. Date and time questions are answered from the local clock. If `TAVILY_API_KEY` is missing or a search fails, the assistant says so instead of guessing. Search results are cached for 15 minutes. Each message adds one routing call to Nemotron, so replies start slightly later.

The default model is `nvidia/nemotron-3.5-bolt-e4b`, matching Interview Studio. You can override it with `LLM_MODEL` or `NVIDIA_MODEL`; `LLM_BASE_URL` defaults to NVIDIA's OpenAI-compatible endpoint. Generic `LLM_API_KEY` remains supported. Secrets take precedence over environment variables. Never commit real keys.

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
