# HTpulse Studio

HTpulse Studio is a Streamlit-based AI content multiplier that transforms a single news article into a multi-format distribution package (video, audio, social, Hindi, SEO, QA) using parallel pipelines and job tracking.

## Architecture Overview

### High-Level Flow
Input → Analysis → Parallel Pipelines → Artifacts → Dashboard

### Core Components
- `main.py`: Streamlit entry point, UI rendering, and view routing (landing vs app).
- `app/core/job_manager.py`: Job creation, async orchestration, pipeline execution, and status tracking.
- `app/storage/db.py`: SQLite persistence for jobs and artifacts.
- `app/pipelines/`: Pipeline implementations (video, audio, social, translation, SEO, QA).
- `app/services/`: Provider adapters (Claude, Ollama, D-ID, Decart/Wav2Lip fallback).
- `app/utils/`: Helpers for validation, logging, retry, media, archive, and style guides.
- `app/ui/landing.html`: Marketing landing page shown before entering the app.

## Tech Stack

- Frontend: Streamlit
- Backend: Python 3.11+ with asyncio orchestration
- Storage: SQLite + local filesystem artifacts
- AI Providers: Ollama (local), Anthropic Claude, D-ID
- Media: FFmpeg, optional Wav2Lip / Decart integration
- Networking: httpx with retries and timeouts

### Data Storage
- SQLite tables: `jobs` (status/progress/errors), `artifacts` (type/path/metadata).
- Local artifacts stored in `app/storage/artifacts/`.

### Async Orchestration
- Analysis runs first.
- All enabled pipelines run in parallel via `asyncio.gather`.
- Errors are captured per pipeline and surfaced in the UI.

## Output Computation Logic

### Workflows (Packs)
- **Editorial Full Pack**: Runs all pipelines — video, audio, social, Hindi, SEO, QA, and analysis. Use for standard newsroom production.
- **Breaking News Fast Pack**: Runs only video, social, SEO, and QA for speed; omits audio/Hindi.
- **Markets Pulse / Youth Summary / Hindi First**: Adjusts tone and audience conditioning in the style guide to shape generation while keeping the same pipeline set.

### Analysis
- `analyze_content()` extracts headline, tone, facts, quotes, entities, and narrative arc.
- Output is validated and saved as structured JSON for downstream pipelines.

### Video
- `generate_video_script()` produces a 60‑second anchor script.
- Video is generated via D‑ID using the configured avatar image URL.

### Audio
- `generate_podcast_script()` creates a 3–5 minute briefing script.
- Local TTS (`say`) generates audio; FFmpeg builds audiogram output.

### Social
- Generates platform‑specific content (thread/article/carousel/post).
- Normalizes and renders in UI cards with download support.

### Hindi
- Full translation with cultural adaptation plus local TTS voiceover.

### SEO
- Headline variants, meta descriptions, FAQs, keywords, internal links.
- Structured JSON output for CMS and scheduler export.

### QA
- Fact-check signals and editorial compliance checks.
- Outputs structured report for review.

## UI Overview

### Landing Page
- Hero value proposition and impact metrics.
- Feature list for video/audio/social/Hindi/SEO/QA.
- CTA routes into the app (`/?app=1`).

### Input Screen
- Paste text, enter URL, or upload file.
- Workflow selector for editorial pack variants.
- Options for voice style, mode, and audience.
- “Generate Content Package” triggers a new job.

### Progress Screen
- Live job status and progress bar.
- Status pills for each pipeline (pending/done/failed).
- Refresh button for manual updates.

### Output Dashboard
Tabbed output for:
- Video: player + scripts and downloads.
- Audio: narration + audiogram output.
- Social: platform-specific content cards.
- Hindi: translation + voiceover.
- SEO: headline variants, meta descriptions, FAQs, keywords.
- QA: fact-check summary and compliance signals.
- Analysis: structured article analysis.

## Environment Configuration
Required keys live in `.env` (not committed):
- `OLLAMA_MODEL`, `ANTHROPIC_API_KEY`, `DID_API_KEY`, `DID_SOURCE_URL`, etc.

## Run Locally
```bash
streamlit run main.py --server.port 8503
```

If using D‑ID, set `DID_SOURCE_URL` to a public avatar image URL (e.g., via ngrok).
