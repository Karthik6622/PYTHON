# AI Book Studio

Turn an idea into a planned, written, reviewed, illustrated and exported book (PDF and DOCX) with a Streamlit app.

- Text: **NVIDIA Nemotron 3.5 Lightning 30B A3B** (`nvidia/nemotron-3.5-lightning-30b-a3b`) through the NVIDIA NIM OpenAI-compatible API, streamed.
- Images: Nemotron only writes the image prompts. Pictures come from a configurable image API, or from a built-in placeholder generator when no image key is set.
- Resumable: every step is saved to `projects/{project_id}/` immediately, so a stopped run continues where it left off.

## 1. Features

- Six tabs: **Create**, **Plan**, **Chapters**, **Images**, **Preview**, **Export**.
- Editable plan, one model request per chapter, automatic quality review with up to two revisions, continuity summaries.
- Book bible (characters, locations, glossary terms or facts and style rules) for consistency.
- Cover (artwork plus real, readable title/subtitle/author text), chapter illustrations with orientation control.
- 6x9 inch PDF with a table of contents and real page numbers; DOCX with heading styles and a TOC field.
- Retry with backoff (2s, 5s, 10s), JSON repair and validation, secret redaction in logs, content screening.

## 2. Architecture

```
app.py                     page config, sidebar, tabs
components/                Streamlit-only UI (state, styles, one module per tab)
services/                  nvidia_client, planner, bible, chapter writer/reviewer,
                           image prompt service, image generator, storage, book_pipeline
generators/                cover, pdf, docx builders (no Streamlit)
prompts/                   all prompt templates, separate from logic
models/                    pydantic models (lenient inputs, strict outputs)
utils/                     retry, JSON extraction, text/Markdown, image, validation helpers
tests/                     pipeline, exporter and UI smoke tests with a fake model
projects/                  saved projects (gitignored)
```

## 3. Pipeline

1. Validate and screen the request. 2. Plan with Nemotron. 3. Validate and normalise the plan.
4. Book bible. 5. Dedication, preface, introduction. 6. Each chapter (one request each).
7. Review. 8. Up to two revisions. 9. Summary. 10. Chapter image prompt. 11. Cover prompt.
12. Chapter images. 13. Cover artwork. 14. Conclusion, glossary, author page. 15. Compose the cover.
16. Build PDF and DOCX. 17. Validate the files.

## 4. Setup

Windows (PowerShell):

```powershell
cd Projects\ai_book_studio
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

macOS / Linux:

```bash
cd Projects/ai_book_studio
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 5. API keys

Create `.streamlit/secrets.toml` (see `.streamlit/secrets.toml.example`) or a `.env` file (see `.env.example`):

```toml
NVIDIA_API_KEY = "nvapi-..."
IMAGE_API_KEY = ""        # optional
```

Keys are read from `st.secrets` first, then environment variables. They are never hard-coded, shown in the UI or written to logs. Both files are gitignored.

## 6. Run

```powershell
python -m streamlit run app.py
```

## 7. Image provider

Set `IMAGE_API_KEY` to use a real provider. The default endpoint is OpenAI-compatible
(`IMAGE_API_URL`, `IMAGE_API_MODEL`, `IMAGE_API_SIZE_*`, `IMAGE_API_RESPONSE_FORMAT`, `IMAGE_API_EXTRA_JSON`).
Both `b64_json` and HTTPS `url` responses are supported. Without a key (or with `IMAGE_PROVIDER=placeholder`) abstract
placeholder art is generated locally and the app clearly flags it as a placeholder. If a real provider fails, the image is replaced by
a placeholder and a warning is shown.

Cloudflare FLUX (`@cf/black-forest-labs/flux-1-schnell`) is used first when `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` are set: it runs on dedicated GPUs and takes seconds per image.
Its free plan has a daily allowance; when it runs out (HTTP 429) the app switches to AI Horde for the following images and tries Cloudflare again later. `CLOUDFLARE_STEPS` (1-8, default 6) sets the quality.
AI Horde (`Flux.1-Schnell fp8 (Compact)` by default: 4 steps and small images, so each image is quick once a worker takes it) is used as the backup, or on its own when only `AI_HORDE_API_KEY` is set (`IMAGE_PROVIDER=cloudflare|ai_horde|api|placeholder` forces a choice).
Requests wait in AI Horde's shared queue, so each image can take from seconds to a few minutes. FLUX always uses 4 steps.
Options: `AI_HORDE_MODEL` (comma separated list), `AI_HORDE_STEPS` (default 16, used by SDXL-type models), `AI_HORDE_FAST_ONLY` (default false; true needs upfront kudos),
`AI_HORDE_TIMEOUT` (seconds to wait per image, default 600) and `AI_HORDE_CONCURRENCY` (images at once, default 3).
Every picture is checked. If it fails or comes back blurry it is generated again (`IMAGE_RETRIES`, default 2 extra tries, with a sharper prompt); a good first image is used at once and the book moves on to the next chapter.
If every try is soft, the sharpest one is kept; the placeholder art is used only when no try produced a picture. `IMAGE_MIN_SHARPNESS` (default 25, 0 turns the blur check off) sets how strict the check is.
To use FLUX on AI Horde, set `AI_HORDE_MODEL=Flux.1-Schnell fp8 (Compact)`. It has far fewer workers, so its queue is often longer than SDXL's.

**Parallel chapters.** `CHAPTER_WORKERS` (default 4, max 8) writes chapters at the same time. Each chapter sees the book bible and the
full outline, plus the summaries of earlier chapters that have already finished. Use `1` for strictly sequential writing; lower it if you hit rate limits.

**Audiobook.** The Audio tab narrates the finished chapters with OpenAI `tts-1` on Pollinations (any book language).
Set `POLLINATIONS_API_KEY` in `.streamlit/secrets.toml` or the environment; the key must allow the audio models and the account needs Pollen. Optional: `POLLINATIONS_TTS_MODEL` (`openai/tts-1` or `openai/tts-1-hd`), `TTS_VOICE` and `TTS_WORKERS` (parallel requests, 1-6); the voice can also be chosen in the tab.
Kokoro on fal.ai (English, Spanish, French) remains available: set `FAL_KEY` instead (or `TTS_PROVIDER=fal`).
fal bills per request. Each section is saved as a WAV file under the project's `audio` folder and finished sections are reused.

## 8. Nemotron settings

Streaming is always on. Only the answer text is kept; reasoning text is discarded. Thinking is off by default for speed and cost:
set `NVIDIA_ENABLE_THINKING=true` and `NVIDIA_REASONING_BUDGET=4096` to enable it. If the endpoint rejects the extra request fields, they are dropped automatically.

## 9. Page counts

The page count is a target. The app reserves pages for the cover and selected front/back matter, converts the rest to a word budget
(about 100 words per page for children's books, 150 for image-heavy books, 300 for fiction, 350 for non-fiction, 400 for technical books),
and reports the real PDF page count after export. Fonts, images and spacing mean the result is approximate.

## 10. Languages and fonts

English, Spanish, French, German, Tamil, Hindi and Japanese are supported. The PDF engine (ReportLab) embeds Unicode fonts but does not shape
complex scripts, so Tamil and Hindi PDFs can look imperfect; the DOCX renders correctly in Word. For Japanese, Tamil and Hindi PDFs
install or drop Noto fonts into `assets/fonts/` (see the README there). Windows fonts (Nirmala UI, Mangal, MS Gothic, Meiryo) are detected automatically.

## 11. Saved projects

```
projects/{project_id}/
  project.json  book_plan.json  book_bible.json  front_matter.json  images.json  generation_status.json
  chapters/chapter_01.md  chapter_01_summary.json  chapter_01_review.json ...
  images/cover_art.png  cover_final.png  chapter_01.png ...
  exports/completed_book.pdf  completed_book.docx
```

All writes are atomic. Use the sidebar to reopen, start a new book, or delete a saved project.

## 11a. Accounts and sign-in

The app opens on a Log in / Create account page. Each book belongs to an account, so projects are still there after a refresh, on another browser or after a restart.

- **Email and password** needs no setup. Passwords are hashed with bcrypt, repeated wrong attempts lock the account for 10 minutes, and the same message is shown for an unknown email and a wrong password.
- **Stay signed in.** A random session token is stored in the `ab_session` cookie (30 days); only its SHA-256 digest is stored on the server. "Log out" ends it.
- **Google and GitHub** buttons are enabled once the matching tables are in `.streamlit/secrets.toml` (see the example file for the exact keys, and keep them at the end of the file). Without them the buttons are shown disabled. Accounts with the same verified email are merged.
- Accounts live in `data/users.db` (gitignored). Books made before accounts existed in the same browser are moved to the account the first time that browser signs in.
- Storage is local disk, so on hosts with an ephemeral file system (some free tiers) accounts and books are lost on redeploy; mount a persistent volume for `data/` and `projects/`.

## 12. Quality review

Each chapter is reviewed by Nemotron acting as an editor. It passes with a score of 80 or more and no critical problems. Failing chapters are revised up to two times;
if they still fail, the best version is accepted automatically (the score and notes stay visible on the Chapters tab) so the book never waits for the user.
If the editor's or the summary's JSON reply cannot be read (even after repair and retries with a larger token limit), the review is skipped and the summary is
taken from the chapter text instead of stopping the run. Temporary API errors are retried automatically. You can still edit, regenerate or review a chapter manually.

For Tamil, Hindi and Japanese, generated text is cleaned of junk symbols and foreign scripts, and paragraphs that still contain English words are rewritten by the model.

## 13. Safety and content policy

Requests for sexual content, hate material, instructions that enable serious harm, reproduction or continuation of existing copyrighted books, imitation of a named
author's style, or damaging claims about real people are declined with an explanation. The model prompts repeat these rules. Generated books should be reviewed by a human before publishing.

## 14. Tests

```powershell
python -m pytest tests -q
```

The tests use a fake model and the placeholder image provider, so no network access or keys are needed.

## 15. Troubleshooting

| Symptom | Fix |
| --- | --- |
| "NVIDIA API key is missing" | Add `NVIDIA_API_KEY` to `.streamlit/secrets.toml` or `.env`, then restart. |
| "Authentication failed" | The key is wrong or lacks access to the model. |
| Run stopped midway | Progress is saved. Open the Plan tab and press **Resume Generation**. |
| Placeholder images | No `IMAGE_API_KEY`, or the provider failed (see the warning on the image). |
| Missing characters in the PDF | Install a Noto font for the language into `assets/fonts/`. |
| PDF page count differs | Expected; see "Page counts". |

## 16. Limitations

- Model output varies; always proofread. Page counts are approximate.
- ReportLab does not shape Tamil/Hindi ligatures perfectly.
- The DOCX table of contents lists chapter names; in Word, right-click it and choose **Update Field** to add page numbers.
- A single Streamlit session runs one generation at a time.
