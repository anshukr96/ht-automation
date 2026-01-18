# HTpulse Studio

HTpulse Studio is a Streamlit-based AI content multiplier that transforms a single news article into a multi-format distribution package (video, audio, social, Hindi, SEO, QA) using parallel pipelines and job tracking.

## Architecture Overview

### High-Level Flow
Input → Analysis → Parallel Pipelines → Artifacts → Dashboard

### Architecture Diagram (High-Level)
```
                 ┌──────────────────────┐
                 │      Streamlit UI     │
                 │  Landing / Input / UI │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │   Job Manager (async) │
                 │  orchestration + state│
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │   Content Analysis   │
                 │   (Claude / Ollama)  │
                 └──────────┬───────────┘
                            │
            ┌───────────────┼────────────────┬────────────────┬───────────────┬───────────────┬───────────────┐
            │               │                │                │               │               │               │
            ▼               ▼                ▼                ▼               ▼               ▼               ▼
     ┌──────────┐    ┌──────────┐     ┌──────────┐     ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
     │  Video   │    │  Audio   │     │  Social  │     │  Hindi   │    │   SEO    │    │    QA    │    │ Analysis │
     │  (D‑ID)  │    │  TTS+FF  │     │  Posts   │     │  TTS     │    │  Pack    │    │  Report  │    │  JSON    │
     └────┬─────┘    └────┬─────┘     └────┬─────┘     └────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘
          │               │                │                │               │               │               │
          └───────────────┴────────────────┴────────────────┴───────────────┴───────────────┴───────────────┘
                                      │
                                      ▼
                           ┌──────────────────────┐
                           │  Artifacts + SQLite  │
                           │ jobs / artifacts / UI│
                           └──────────────────────┘
```

### Core Components
- `main.py`: Streamlit entry point, UI rendering, and view routing (landing vs app).
- `app/core/job_manager.py`: Job creation, async orchestration, pipeline execution, and status tracking.
- `app/storage/db.py`: SQLite persistence for jobs and artifacts.
- `app/pipelines/`: Pipeline implementations (video, audio, social, translation, SEO, QA).
- `app/services/`: Provider adapters (Claude, Ollama, D-ID, fallback).
- `app/utils/`: Helpers for validation, logging, retry, media, archive, and style guides.
- `app/ui/landing.html`: Marketing landing page shown before entering the app.

## Tech Stack

- Frontend: Streamlit
- Backend: Python 3.11+ with asyncio orchestration
- Storage: SQLite + local filesystem artifacts
- AI Providers: Ollama (local),  D-ID
- Media: FFmpeg
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
- Uses strict JSON extraction and repair to keep structure consistent.

### Video
- `generate_video_script()` produces a 60‑second anchor script.
- Script is enforced to stay within 130–170 words for timing.
- Video is generated via D‑ID using the configured avatar image URL.

### Audio
- `generate_podcast_script()` creates a 3–5 minute briefing script.
- Local TTS (`say`) generates audio; FFmpeg builds audiogram output.
- Voice selection is based on avatar gender hints and environment config.

### Social
- Generates platform‑specific content (thread/article/carousel/post).
- Normalizes output into platform-safe fields for UI cards and exports.

### Hindi
- Full translation with cultural adaptation plus local TTS voiceover.
- Named entities are preserved to maintain editorial accuracy.

### SEO
- Headline variants, meta descriptions, FAQs, keywords, internal links.
- Structured JSON output for CMS and scheduler export.
- Output is validated for required keys before saving.

### QA
- Fact-check signals and editorial compliance checks.
- Fact verification runs against web search results with confidence scores.
- Readability scored (Flesch) and prohibited phrase checks applied.
- Outputs structured report for review.

## Prompt Library (Core Prompts)

These are the primary prompt templates used across analysis and generation flows. They are shared between Claude and the local LLM fallback.

### Content Analysis
```
Analyze this news article and extract:
1. Headline, category, tone (neutral/urgent/investigative)
2. Key facts (list all verifiable claims)
3. Key quotes (with attribution)
4. Named entities (people, places, organizations)
5. Narrative arc (setup, conflict, resolution)

Article: {article_text}

Return as structured JSON.
```

### Video Script (60s)
```
Write a 60-second news anchor script for a video segment.
Source: {headline} - {category}
Key Facts: {facts}
Tone: {tone}

Requirements:
- 130-170 words (60 seconds at 130-170 wpm)
- Professional, confident anchor voice
- No section labels like Hook/Body/Conclusion
- No stage directions, just spoken narration
- Include 1-2 key statistics or quotes
- End with CTA: "Read full article at HT.com"

Output only the script.
```

### Podcast Script (3–5 min)
```
Write a 3-minute podcast script for a news briefing.
Headline: {headline}
Key Facts: {facts}
Tone: {tone}

Requirements:
- 450-650 words
- Conversational, clear pacing
- No section labels
- End with CTA: "Read full article at HT.com"
```

### Social Package
```
Generate platform-specific social content:
- Twitter thread (5-7 tweets)
- LinkedIn post (500-700 words)
- Instagram carousel copy (5 slides + caption)
- Facebook post (200-300 words)
- WhatsApp summary (150 words)

Return strict JSON with keys:
twitter_thread, linkedin, instagram, facebook, whatsapp
```

### Hindi Translation
```
Translate the full article into Hindi with cultural adaptation, not literal translation.
Preserve named entities and proper nouns.

Headline: {headline}
Entities: {entities}
Article: {article_text}

Return JSON with keys: hindi_text, notes.
```

### SEO Package
```
Create an SEO package for the article.
Return JSON with keys:
headline_variants (10), meta_descriptions (3),
faqs (5 question/answer), keywords (10-15), internal_links (3).
```

### QA / Fact Verification
```
Verify the claim using the provided sources.
Respond in JSON with keys: verified, confidence, sources.
Claim: {fact}
Sources: {sources}
```

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
