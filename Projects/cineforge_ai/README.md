# 🎬 CineForge AI

CineForge AI is a Streamlit app that turns a text description into a short, YouTube-ready AI video using the
**NVIDIA Cosmos3-Nano** hosted API. It adds a local prompt-enhancement engine, a YouTube publishing package
(titles, description, hashtags, tags, thumbnail prompt, hook), a multi-scene storyboard mode and a session
gallery of your creations.

## Main features

- **Text to Video** – prompt → enhanced prompt (editable) → NVIDIA request → Base64 decode → MP4 preview → download.
- **Local prompt enhancement** – combines subject, content type, platform composition, style, camera, lighting,
  depth/focus, motion consistency, quality wording and pacing. No second paid AI API is used.
- **YouTube Package** – suggested title, 5 alternatives, description, hashtags, tags, thumbnail prompt, opening hook,
  on-screen caption and a safe filename (generated locally from templates).
- **Multi-Scene Storyboard (experimental)** – 2–6 editable scene cards sharing one style prefix, generated one by one.
  Optional merge / crossfade / user-supplied audio when FFmpeg is installed.
- **My Creations** – up to 20 items per session with preview, download, regenerate and confirmed delete.
- **Safe by design** – key only from secrets/env, redacted errors, UUID filenames, per-session temp folders,
  duplicate-request protection, file validation.
- *Image to Video* and *Video to Video* tabs show "Coming soon" because their request schemas are not implemented.

## Project structure

```text
cineforge_ai/
├── app.py                  # Streamlit UI, session state, generation workflow
├── api_client.py           # NVIDIA request, error mapping, Base64 decoding
├── prompt_engine.py        # Sanitising, validation, prompt enhancement, scene prompts
├── youtube_tools.py        # Local YouTube package generator
├── video_utils.py          # Temp-file handling, audio validation, FFmpeg merge
├── config.py               # Endpoint, confirmed payload schema, option lists, limits
├── requirements.txt
├── .env.example
├── .gitignore
├── .streamlit/
│   ├── config.toml         # Dark theme
│   └── secrets.toml.example
└── tests/test_core.py      # Unit + end-to-end UI tests (network mocked)
```

## Local installation

```bash
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
```

macOS/Linux:

```bash
source venv/bin/activate
```

Then:

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Get an NVIDIA API key and accept the trial terms

1. Sign in at <https://build.nvidia.com> with an NVIDIA account.
2. Open the Cosmos3-Nano model page: <https://build.nvidia.com/nvidia/cosmos3-nano>.
3. Accept the API trial terms shown on the page and confirm that the hosted endpoint is enabled for your account.
4. Choose **Get API Key** and copy the key (it starts with `nvapi-`).

## Configure the API key

**Streamlit secrets (recommended)** – copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`:

```toml
NVIDIA_API_KEY = "nvapi-your-key-here"
```

**.env (local fallback)** – copy `.env.example` to `.env`:

```text
NVIDIA_API_KEY=nvapi-your-key-here
```

Secrets take priority over the environment variable. Both files are git-ignored. Never commit a real key.

## Deploy on Streamlit Community Cloud

1. Push the project to GitHub (without `secrets.toml` or `.env`).
2. Create a new app on <https://share.streamlit.io>, pointing at `app.py`.
3. Under **Advanced settings → Secrets**, paste `NVIDIA_API_KEY = "nvapi-..."`.
4. Optional: add a `packages.txt` containing `ffmpeg` to enable clip merging.

## Security warnings

- Do not paste your API key into the UI, issues, logs or screenshots. The app never prints or stores it.
- Rotate the key immediately if it is ever exposed.
- Prompts and outputs sent to NVIDIA may be logged under NVIDIA's API trial terms. **Do not submit confidential or
  personal data.**
- Generated Cosmos3 images and videos may contain **SynthID** watermarking.
- Uploaded audio must be yours or properly licensed. The app does not generate music.

## Known Preview API limitations

- Cosmos3-Nano is a Preview endpoint; its schema, limits and availability can change.
- Only `model_mode`, `prompt` and `negative_prompt` are sent. Duration, aspect ratio, resolution, FPS, seed, motion
  and guidance are **not confirmed** request fields, so they only shape the prompt wording.
- Output length, resolution and quality are controlled by the model. Requested duration is a pacing hint only.
- The app expects a synchronous response with `b64_video`. Asynchronous (HTTP 202) responses are not supported.
- Separate storyboard clips will not have perfect character or object consistency.

**Updating the schema:** all schema-dependent lines are isolated in `config.py` and marked `[SCHEMA]`. Copy the JSON
body from NVIDIA's **View API Code** panel and adjust `build_payload`, `MODEL_MODE_TEXT2VIDEO`,
`RESPONSE_VIDEO_FIELD` and `SUPPORTED_OPTIONAL_PARAMS` only.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| "NVIDIA API key missing" | No secret or env variable | Add `NVIDIA_API_KEY` to `.streamlit/secrets.toml` or `.env`, restart |
| 401 Authentication failed | Invalid, expired or revoked key | Create a new key on build.nvidia.com |
| 403 Access denied | Trial terms not accepted / endpoint not enabled | Open the model page, accept the terms, confirm access |
| 404 Endpoint not found | Endpoint URL changed | Compare `API_URL` with "View API Code" |
| 422 Invalid request field | Preview schema changed | Update the `[SCHEMA]` lines in `config.py` |
| 429 Rate limit | Free-trial or rate limit reached | Wait and retry later |
| Timeout | Generation took over 600 s | Retry with a simpler prompt |
| "Unsupported video format" | Output was not an MP4 | Retry; report if persistent |
| "FFmpeg was not found" | FFmpeg missing | Install FFmpeg (see the in-app hint) and restart |

## Commercial use and licensing

Check the NVIDIA API trial terms, the Cosmos model license and the terms of any platform you publish to before using
generated videos commercially. The trial API is intended for evaluation, not production workloads. You are
responsible for disclosing AI-generated content where required.

## Run the tests

```bash
pip install pytest
python -m pytest tests -q
```

## Screenshots

_Add screenshots here (Text to Video, Storyboard, My Creations)._
