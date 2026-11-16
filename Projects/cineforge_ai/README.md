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
- **AI Director** – a Nemotron model (3.5 Super VL 120B, 3.5 Lightning 30B or 3 Ultra 550B) writes the video prompt and
  narration; falls back to the local prompt engine if the model is unreachable. Needs `NVIDIA_API_KEY`.
- **Voice-over + YouTube export** – narration is synthesized with a free Microsoft neural voice (`edge-tts`) and the
  video is mastered to Full HD H.264/AAC with FFmpeg (`imageio-ffmpeg` is bundled).
- **Progress bar** – one overall percentage across prompt writing, rendering, voice-over and export.
- The *Video to Video* tab shows "Coming soon" because its request schema is not implemented.

## Project structure

```text
cineforge_ai/
├── app.py                  # Streamlit UI, session state, generation workflow
├── api_client.py           # NVIDIA request, error mapping, Base64 decoding
├── llm_client.py           # AI Director (Nemotron) prompt + narration writer
├── audio_tools.py          # Voice-over synthesis and Full HD YouTube export
├── picture_video.py        # Quota-free fallback: AI key-frames + camera motion + crossfades
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

## Free video provider (default)

Out of the box the app uses **LTX-Video** on the public Hugging Face Space
[`Lightricks/ltx-video-distilled`](https://huggingface.co/spaces/Lightricks/ltx-video-distilled) through
`gradio_client`. It is free and needs **no API key**. Limits: clips up to 8.5 s at 24 fps, generation usually takes
1-3 minutes, and anonymous use shares a small daily ZeroGPU quota. A free Hugging Face token raises that quota; set
`HF_TOKEN` in `.streamlit/secrets.toml` or `.env`. When the quota is used up (or the Space is down) the app
automatically switches to a **quota-free renderer**: 2-3 AI key-frames from the free Pollinations image API, each
animated with a slow camera move and joined with crossfades (needs FFmpeg, bundled via `imageio-ffmpeg`). It is
less dynamic than real AI motion, and the free image tier allows one picture per 45 s per IP, so it takes about
1-2 minutes; a free `POLLINATIONS_API_KEY` (https://enter.pollinations.ai) removes that limit and allows up to 6
shots. Set `VIDEO_PROVIDER=pictures` to always use it. To use NVIDIA instead, set `VIDEO_PROVIDER=nvidia` and
follow the next section.

## Optional: NVIDIA provider - get an API key and accept the trial terms

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
Optionally set `NVIDIA_API_URL` the same way to override the invocation URL. For a self-hosted Cosmos3 server
(for example a NIM, which serves `POST /v1/infer`), set `NVIDIA_API_URL=http://<host>:8000/v1/infer`; no API key is
needed for non-`nvidia.com` URLs. The server must accept the same request fields and return `b64_video`.

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
- The app sends `model_mode`, `prompt`, `negative_prompt` plus the documented optional fields `resolution`,
  `num_frames`, `fps`, `num_inference_steps`, `guidance_scale` and `seed`. Everything else (content type, style,
  camera, lighting, motion, creativity) only shapes the prompt text.
- Mapping: Platform → `resolution` aspect (16:9, 9:16, 1:1; 21:9 falls back to 16:9), Quality → resolution tier
  (Draft 256p / Standard 480p / High 720p) and steps, Duration → `num_frames` at 24 fps (max ≈16 s / 12 s / 8 s per
  tier), Prompt adherence → `guidance_scale`, Seed → `seed` (0 = random).
- Returned videos use a VP9 track inside an MP4; use a compatible player (current Chrome/Edge/Firefox work).
- The app expects a synchronous response with `b64_video`. Asynchronous (HTTP 202) responses are not supported.
- Separate storyboard clips will not have perfect character or object consistency.

**Updating the schema:** all schema-dependent lines are isolated in `config.py` and marked `[SCHEMA]`.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| "Rate limit reached" with the free provider | Quota used up and the fallback renderer also failed (e.g. image limit, no internet) | Wait and retry, add a free `HF_TOKEN` or `POLLINATIONS_API_KEY` |
| "Hugging Face Space could not generate the video" | The free Space is busy or restarting | Retry in a minute; use **Test API connection** to check it is running |
| "NVIDIA API key missing" | No secret or env variable | Add `NVIDIA_API_KEY` to `.streamlit/secrets.toml` or `.env`, restart |
| 401 Authentication failed | Invalid, expired or revoked key | Create a new key on build.nvidia.com |
| 403 Access denied | Trial terms not accepted / endpoint not enabled | Open the model page, accept the terms, confirm access |
| 404 Endpoint not found | NVIDIA's gateway does not serve the URL (it returned 404 even for requests without a valid key when this was checked) | Copy the invocation URL from the model page's **View API Code** panel into `NVIDIA_API_URL` (secrets or `.env`); a self-hosted NIM uses `http://<host>:8000/v1/infer`. Use **Test API connection** in the sidebar to re-check |
| 422 Invalid request field | Preview schema changed or a value is out of range | Compare with "View API Code" and update the `[SCHEMA]` lines in `config.py` |
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
