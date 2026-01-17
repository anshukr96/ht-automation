import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Dict

ROOT_DIR = Path(__file__).parent
DEFAULT_TITLE = "HTpulse Studio"
DEMO_ARTICLE_PATH = ROOT_DIR / "app" / "storage" / "demo_article.txt"

try:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=ROOT_DIR / ".env")
except Exception:
    pass

import streamlit as st
import streamlit.components.v1 as components
from html import escape
import urllib.parse

from app.core.job_manager import JobManager
from app.utils.local_server import ensure_asset_server, get_asset_url
from app.utils.archive import build_zip
from app.utils.extract import extract_article_from_url
from app.utils.validation import ValidationError, validate_article


def main() -> None:
    st.set_page_config(page_title=DEFAULT_TITLE, layout="wide")
    _inject_theme()
    ensure_asset_server(ROOT_DIR / "app" / "ui" / "assets")
    job_manager = JobManager()
    view = _resolve_view()
    if view == "landing":
        _render_landing()
        return

    _render_header(job_manager)

    if "job_id" not in st.session_state:
        st.session_state.job_id = None
    if st.session_state.job_id:
        _render_progress(job_manager)
        return

    _render_input(job_manager)


def _render_header(job_manager: JobManager) -> None:
    col1, col2 = st.columns([4, 1])
    with col1:
        st.markdown(
            """\
            <div class="lm-hero">
              <div class="lm-kicker">HTpulse Studio</div>
              <h1>HTpulse Studio</h1>
              <p>Turn one story into a full distribution pack in minutes — video, audio, social, Hindi, SEO, QA.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        if _demo_mode_enabled():
            st.markdown('<div class="lm-hero-action">', unsafe_allow_html=True)
            if st.button("Run Demo Article"):
                _run_demo(job_manager)
            st.markdown("</div>", unsafe_allow_html=True)
    did_source_url = os.getenv("DID_SOURCE_URL", "")
    if not did_source_url:
        local_url = get_asset_url("lm-anchor.webp")
        if local_url:
            st.info(
                f"D-ID needs a public avatar URL. Local preview: {local_url}. "
                "Use a tunnel (ngrok) or upload to a public host.",
                icon="ℹ️",
            )


def _inject_theme() -> None:
    st.markdown(
        """\
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@500;600;700&family=Manrope:wght@300;400;500;600;700&display=swap');
        :root {
            --lm-ink: #0f1a13;
            --lm-green: #1d4ed8;
            --lm-emerald: #1e40af;
            --lm-lime: #dbeafe;
            --lm-cream: #eff6ff;
            --lm-gold: #2563eb;
            --lm-slate: #3b4b40;
            --lm-surface: #ffffff;
            --lm-surface-alt: #f7f5f0;
        }
        html, body, [class*="css"]  {
            font-family: 'Manrope', sans-serif;
            color: var(--lm-ink);
        }
        .stApp {
            background: #ffffff;
        }
        .block-container {
            padding-top: 2.25rem;
            max-width: 1200px;
        }
        h1, h2, h3 {
            font-family: 'Playfair Display', serif;
            color: var(--lm-ink);
        }
        .lm-hero {
            padding: 12px 0 8px 0;
        }
        .lm-kicker {
            text-transform: uppercase;
            letter-spacing: 0.2em;
            font-size: 20px;
            color: var(--lm-gold);
            font-weight: 600;
            margin-bottom: 6px;
        }
        .lm-hero-action {
            display: flex;
            justify-content: flex-end;
            align-items: flex-start;
            height: 100%;
            padding-top: 18px;
        }
        .lm-hero-action .stButton > button {
            background: var(--lm-gold);
            color: #fff;
            border-radius: 999px;
            padding: 6px 14px;
            font-weight: 600;
        }
        .stButton > button {
            background: var(--lm-gold);
            color: #fff;
            border-radius: 999px;
            padding: 8px 18px;
            font-weight: 600;
        }
        .lm-tip {
            margin-top: 8px;
            padding: 10px 12px;
            border-radius: 12px;
            background: #fff6e8;
            color: #8a4f00;
            font-size: 0.9rem;
            border: 1px solid rgba(249, 157, 28, 0.25);
        }
        .lm-hero p {
            font-size: 1rem;
            color: var(--lm-slate);
            margin-top: 6px;
            max-width: 680px;
        }
        .lm-metric {
            background: var(--lm-surface);
            border: 1px solid rgba(15, 26, 19, 0.08);
            border-radius: 16px;
            padding: 18px;
            box-shadow: 0 12px 24px rgba(15, 26, 19, 0.08);
        }
        .lm-metric-label {
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            color: var(--lm-emerald);
            font-weight: 600;
        }
        .lm-metric-value {
            font-size: 2.1rem;
            font-family: 'Playfair Display', serif;
            color: var(--lm-ink);
            margin: 6px 0;
        }
        .lm-metric-sub {
            color: var(--lm-slate);
            font-size: 0.9rem;
        }
        .lm-card {
            background: var(--lm-surface);
            border: 1px solid rgba(15, 26, 19, 0.08);
            border-radius: 18px;
            padding: 16px;
            box-shadow: 0 14px 30px rgba(15, 26, 19, 0.06);
        }
        .stButton > button:hover {
            background: var(--lm-emerald);
            color: #fff;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, var(--lm-cream) 0%, var(--lm-surface) 100%);
            border-right: 1px solid rgba(15, 26, 19, 0.08);
        }
        [data-testid="stSidebar"] h2 {
            font-family: 'Playfair Display', serif;
        }
        [data-testid="stTabBar"] button {
            border-radius: 999px;
            padding: 6px 16px;
        }
        [data-testid="stTabBar"] button[aria-selected="true"] {
            background: var(--lm-lime);
            color: var(--lm-ink);
            border: 1px solid rgba(15, 26, 19, 0.1);
        }
        .lm-status-grid {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            margin-top: 8px;
        }
        .lm-status {
            border-radius: 999px;
            padding: 6px 12px;
            font-size: 0.85rem;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            border: 1px solid rgba(15, 26, 19, 0.08);
            background: #f7f5f0;
            color: #29332c;
            width: fit-content;
            box-shadow: 0 6px 14px rgba(15, 26, 19, 0.08);
        }
        .lm-status-done {
            background: #13804a;
            color: #ffffff;
            border-color: rgba(19, 128, 74, 0.4);
        }
        .lm-status-pending {
            background: #fff6e8;
            color: #8a4f00;
            border-color: rgba(249, 157, 28, 0.25);
        }
        .lm-status-failed {
            background: #f7d2d2;
            color: #7a0d0d;
            border-color: rgba(156, 27, 27, 0.35);
        }
        .lm-status-skipped {
            background: #eef1f6;
            color: #4b5563;
            border-color: rgba(75, 85, 99, 0.2);
        }
        [data-testid="stTabs"] [data-baseweb="tab-list"] {
            border-bottom: none;
        }
        .stProgress > div > div {
            background-image: linear-gradient(90deg, var(--lm-green), var(--lm-gold));
        }
        .stVideo video {
            max-height: 600px;
            width: 100%;
            object-fit: contain;
        }
        @media (prefers-color-scheme: dark) {
            :root {
                --lm-ink: #f1f5f2;
                --lm-slate: #d3ddd6;
                --lm-cream: #0e1411;
                --lm-surface: #0b120f;
                --lm-surface-alt: #121a16;
                --lm-lime: #2b5a49;
            }
            .stApp {
                background: #0b120f;
            }
            .lm-metric,
            .lm-card {
                border-color: rgba(255, 255, 255, 0.08);
                box-shadow: 0 12px 30px rgba(0, 0, 0, 0.35);
            }
            [data-testid="stSidebar"] {
                background: #0f1612;
                border-right: 1px solid rgba(255, 255, 255, 0.06);
            }
            [data-testid="stTabBar"] button[aria-selected="true"] {
                border-color: rgba(255, 255, 255, 0.12);
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_input(job_manager: JobManager) -> None:
    st.subheader("Input Your Article")
    tabs = st.tabs(["Paste Text", "Enter URL", "Upload File"])
    with tabs[0]:
        paste_text = st.text_area(
            "Paste your article here",
            height=260,
            placeholder="Paste your article text here (include a headline on the first line).",
        )

    with tabs[1]:
        url_text = st.text_input(
            "Article URL",
            placeholder="https://example.com/news/article",
        )
        st.caption("URL fetching runs in the background when you click Generate.")
        if "preview_text" not in st.session_state:
            st.session_state.preview_text = ""
        if st.button("Preview URL"):
            try:
                st.session_state.preview_text = asyncio.run(extract_article_from_url(url_text))
            except Exception as exc:
                st.error(f"Preview failed: {exc}")
        if st.session_state.preview_text:
            st.text_area(
                "Extracted article preview",
                value=st.session_state.preview_text[:5000],
                height=200,
            )

    with tabs[2]:
        uploaded = st.file_uploader("Upload a .txt file", type=["txt"])
        upload_text = ""
        if uploaded is not None:
            upload_text = uploaded.read().decode("utf-8", errors="ignore")

    st.markdown('<div class="lm-card">', unsafe_allow_html=True)
    st.write("Use Case")
    _ensure_use_case_defaults()
    use_case = st.selectbox(
        "Choose a workflow",
        [
            "Editorial Full Pack",
            "Breaking News Fast Pack",
            "Markets Pulse",
            "Youth Summary",
            "Hindi First",
        ],
        key="use_case",
        on_change=_apply_use_case_defaults,
    )
    st.info(_use_case_description(use_case))

    st.write("Options")
    opt_col1, opt_col2, opt_col3 = st.columns([1.1, 1.1, 1.8])
    with opt_col1:
        st.caption("Voice")
        use_style = st.toggle("Mint Flavor", key="use_style")
    with opt_col2:
        st.caption("Mode")
        fast_mode = st.toggle("Breaking-News", key="fast_mode")
    with opt_col3:
        st.caption("Audience")
        audience = st.selectbox(
            "Audience",
            ["General", "Markets", "Youth", "Hindi-first"],
            index=["General", "Markets", "Youth", "Hindi-first"].index(st.session_state.get("audience", "General")),
            key="audience",
            label_visibility="collapsed",
        )
    outputs = _outputs_for_mode(fast_mode)
    st.caption(f"Outputs: {', '.join(outputs)}")

    if st.button("Generate Content Package", type="primary"):
        try:
            source_type, source_payload = _select_source(paste_text, url_text, upload_text)
            if source_type == "paste":
                validate_article(source_payload)
            job_id = job_manager.create_job()
            job_manager.start_analysis(job_id, source_type, source_payload, use_style, audience, fast_mode)
            st.session_state.job_id = job_id
            st.rerun()
        except ValidationError as exc:
            st.error(str(exc))
        except ValueError as exc:
            st.error(str(exc))

    # Demo button is placed in the header.
    st.markdown("</div>", unsafe_allow_html=True)


def _render_landing() -> None:
    st.session_state.job_id = None
    landing_path = ROOT_DIR / "app" / "ui" / "landing.html"
    if landing_path.exists():
        components.html(landing_path.read_text(encoding="utf-8"), height=2200, scrolling=True)
    # Landing page stays focused on the core content.


def _resolve_view() -> str:
    if "view" not in st.session_state:
        st.session_state.view = "landing"
    try:
        app_param = st.query_params.get("app", "")
    except Exception:
        app_param = st.experimental_get_query_params().get("app", [""])[0]
    if app_param:
        st.session_state.view = "app"
    return st.session_state.view


def _render_progress(job_manager: JobManager) -> None:
    job_id = st.session_state.job_id
    if not job_id:
        return

    job = job_manager.get_job(job_id)
    if not job:
        st.error("Job not found. Please start again.")
        st.session_state.job_id = None
        return

    components.html("<script>window.scrollTo(0, 0);</script>", height=0)
    st.subheader("Generating Content Package")
    st.progress(job.progress)
    st.write(f"Status: {job.status}")
    _render_progress_steps(job_manager, job_id)

    if job.status in {"running", "queued", "generating"}:
        st.caption("Click refresh to update pipeline status.")
        if st.button("Refresh Status"):
            st.rerun()

    if job.status == "failed":
        st.error(job.error or "Unknown error")
        if st.button("Start New Job"):
            st.session_state.job_id = None
            st.rerun()
        return

    if job.status in {"completed", "completed_with_errors"}:
        if job.status == "completed_with_errors":
            st.warning(job.error or "Completed with errors.")
        else:
            st.success("Content package ready.")
        _render_dashboard(job_manager, job_id)
        if st.button("Start New Job"):
            st.session_state.job_id = None
            st.rerun()


def _select_source(paste_text: str, url_text: str, upload_text: str) -> tuple[str, str]:
    if paste_text.strip():
        return "paste", paste_text
    if url_text.strip():
        return "url", url_text.strip()
    if upload_text.strip():
        return "upload", upload_text
    raise ValueError("Provide article text, URL, or upload a file.")


def _render_dashboard(job_manager: JobManager, job_id: str) -> None:
    artifacts = job_manager.list_artifacts(job_id)
    artifacts_by_type = {artifact["type"]: artifact for artifact in artifacts}
    errors = [artifact for artifact in artifacts if artifact["type"].startswith("error_")]
    if errors:
        st.warning("Some pipelines failed. See details below.")
        for artifact in errors:
            st.caption(f"{artifact['type']}: {artifact.get('metadata', {}).get('error', 'Unknown error')}")
    zip_bytes = build_zip([artifact["path"] for artifact in artifacts])
    if zip_bytes:
        st.download_button("Download All", zip_bytes, file_name=f"{job_id}_package.zip")
    _render_publish_pack(artifacts_by_type)

    enabled = _enabled_pipelines_from_artifacts(artifacts_by_type)
    tab_labels = [label for label in ["Video", "Audio", "Social", "Hindi", "SEO", "QA", "Analysis"] if label in enabled]
    tabs = st.tabs(tab_labels)
    for label, tab in zip(tab_labels, tabs, strict=False):
        with tab:
            if label == "Video":
                _render_video_tab(job_id, artifacts_by_type)
            elif label == "Audio":
                _render_audio_tab(artifacts_by_type)
            elif label == "Social":
                _render_social_tab(job_id, artifacts_by_type)
            elif label == "Hindi":
                _render_hindi_tab(job_id, artifacts_by_type)
            elif label == "SEO":
                _render_seo_tab(job_id, artifacts_by_type)
            elif label == "QA":
                _render_qa_tab(artifacts_by_type)
            elif label == "Analysis":
                _render_analysis_tab(artifacts_by_type)


def _render_progress_steps(job_manager: JobManager, job_id: str) -> None:
    artifacts = job_manager.list_artifacts(job_id)
    types = {artifact["type"] for artifact in artifacts}
    error_types = {artifact["type"] for artifact in artifacts if artifact["type"].startswith("error_")}
    enabled = _enabled_pipelines_from_artifacts({artifact["type"]: artifact for artifact in artifacts})
    cards = []
    steps = [
        ("Analysis", {"analysis"}, "error_analysis"),
        ("Video", {"video_branded", "video_raw"}, "error_video"),
        ("Audio", {"audiogram", "audio"}, "error_audio"),
        ("Social", {"social"}, "error_social"),
        ("Hindi", {"translation"}, "error_translation"),
        ("SEO", {"seo"}, "error_seo"),
        ("QA", {"qa"}, "error_qa"),
    ]
    for label, artifact_types, error_type in steps:
        if label not in enabled:
            status = "skipped"
        elif error_type in error_types:
            status = "failed"
        elif types.intersection(artifact_types):
            status = "done"
        else:
            status = "pending"
        icon = {
            "done": "✅",
            "pending": "⏳",
            "failed": "⚠️",
            "skipped": "⏭️",
        }.get(status, "⏳")
        css_class = f"lm-status lm-status-{status}"
        cards.append(f"<div class='{css_class}'>{icon} {label}</div>")
    st.markdown(f"<div class='lm-status-grid'>{''.join(cards)}</div>", unsafe_allow_html=True)


def _render_video_tab(job_id: str, artifacts: Dict[str, Any]) -> None:
    video = artifacts.get("video_branded") or artifacts.get("video_raw")
    if not video:
        st.info("Video not available yet.")
        return
    meta = video.get("metadata", {})
    if meta.get("lipsync") == "fallback":
        st.warning("Lip-sync not available; showing motion fallback. Check Wav2Lip setup.")
    if video["path"].endswith(".mp4") and os.path.exists(video["path"]):
        st.video(video["path"])
        st.download_button("Download Video", _read_bytes(video["path"]), file_name=os.path.basename(video["path"]))
    else:
        st.text("Video placeholder generated (non-mp4).")
        st.download_button("Download Video", _read_bytes(video["path"]), file_name=os.path.basename(video["path"]))
    script = artifacts.get("video_script")
    if script:
        content = _read_text(script["path"])
        st.text_area("Video script", value=content, height=200, key=f"video_script_{job_id}")


def _render_audio_tab(artifacts: Dict[str, Any]) -> None:
    audio = artifacts.get("audio")
    if not audio:
        st.info("Audio not available yet.")
        return
    if os.path.exists(audio["path"]):
        st.audio(audio["path"])
        st.download_button("Download Audio", _read_bytes(audio["path"]), file_name=os.path.basename(audio["path"]))
    audiogram = artifacts.get("audiogram")
    if audiogram and audiogram["path"].endswith(".mp4"):
        st.video(audiogram["path"])


def _render_social_tab(job_id: str, artifacts: Dict[str, Any]) -> None:
    social = artifacts.get("social")
    if not social:
        st.info("Social posts not available yet.")
        return
    content = _safe_json_loads(_read_text(social["path"]))
    if not content:
        st.warning("Social content is malformed; showing raw output.")
        st.text_area("Social raw output", value=_read_text(social["path"]), height=240, key=f"social_raw_{job_id}")
        return
    twitter_items = _coerce_list(content.get("twitter_thread", []))
    _render_social_carousel(
        "Twitter thread",
        twitter_items,
        job_id,
        "twitter",
        "\n".join(twitter_items),
    )
    _render_social_carousel(
        "LinkedIn",
        [content.get("linkedin", "")],
        job_id,
        "linkedin",
        content.get("linkedin", ""),
    )
    instagram = content.get("instagram", {})
    instagram_items = _filter_instagram_slides(_coerce_list(instagram.get("slides", [])))
    _render_social_carousel(
        "Instagram",
        instagram_items if instagram_items else [str(instagram.get("caption", ""))],
        job_id,
        "instagram",
        f"Caption: {instagram.get('caption', '')}\n\nSlides:\n" + "\n".join(instagram_items),
    )
    _render_social_carousel(
        "Facebook",
        [content.get("facebook", "")],
        job_id,
        "facebook",
        content.get("facebook", ""),
    )
    _render_social_carousel(
        "WhatsApp",
        [content.get("whatsapp", "")],
        job_id,
        "whatsapp",
        content.get("whatsapp", ""),
    )
    st.download_button(
        "Download Social JSON",
        _read_bytes(social["path"]),
        file_name=os.path.basename(social["path"]),
    )


def _render_hindi_tab(job_id: str, artifacts: Dict[str, Any]) -> None:
    translation = artifacts.get("translation")
    if not translation:
        st.info("Hindi translation not available yet.")
        return
    raw_content = _read_text(translation["path"])
    content = _extract_json_field(raw_content, "hindi_text") or raw_content
    st.text_area("Hindi translation", value=content, height=240, key=f"hindi_{job_id}")
    st.download_button(
        "Download Hindi",
        _read_bytes(translation["path"]),
        file_name=os.path.basename(translation["path"]),
    )
    voiceover = artifacts.get("translation_audio")
    if voiceover and voiceover["path"].endswith(".mp3"):
        st.audio(voiceover["path"])


def _render_seo_tab(job_id: str, artifacts: Dict[str, Any]) -> None:
    seo = artifacts.get("seo")
    if not seo:
        st.info("SEO package not available yet.")
        return
    content = _read_text(seo["path"])
    st.text_area("SEO JSON", value=content, height=240, key=f"seo_{job_id}")
    st.download_button("Download SEO JSON", _read_bytes(seo["path"]), file_name=os.path.basename(seo["path"]))


def _render_qa_tab(artifacts: Dict[str, Any]) -> None:
    qa = artifacts.get("qa")
    if not qa:
        st.info("QA report not available yet.")
        return
    content = _safe_json_loads(_read_text(qa["path"]))
    if content:
        st.json(content)
    else:
        st.warning("QA output is malformed; showing raw output.")
        st.text_area("QA raw output", value=_read_text(qa["path"]), height=240)
    st.download_button("Download QA JSON", _read_bytes(qa["path"]), file_name=os.path.basename(qa["path"]))


def _render_analysis_tab(artifacts: Dict[str, Any]) -> None:
    analysis = artifacts.get("analysis")
    if not analysis:
        st.info("Analysis not available.")
        return
    content = _safe_json_loads(_read_text(analysis["path"]))
    if content:
        st.json(content)
    else:
        st.warning("Analysis output is malformed; showing raw output.")
        st.text_area("Analysis raw output", value=_read_text(analysis["path"]), height=240)
    metadata = analysis.get("metadata", {})
    if metadata:
        st.caption(f"Model: {metadata.get('model')} | Cost (USD): {metadata.get('cost_usd')}")


def _read_bytes(path: str) -> bytes:
    if not os.path.exists(path):
        return b""
    with open(path, "rb") as handle:
        return handle.read()


def _read_text(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()




def _write_text(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def _safe_json_loads(raw: str) -> Dict[str, Any] | None:
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _extract_json_field(raw: str, field: str) -> str | None:
    parsed = _safe_json_loads(raw)
    if isinstance(parsed, dict) and field in parsed:
        return str(parsed.get(field) or "").strip()
    pattern = rf'"{re.escape(field)}"\\s*:\\s*"(.+?)"'
    match = re.search(pattern, raw, re.DOTALL)
    if not match:
        pattern = rf"'{re.escape(field)}'\\s*:\\s*'(.+?)'"
        match = re.search(pattern, raw, re.DOTALL)
        if not match:
            return None
    snippet = match.group(1)
    try:
        return json.loads(f"\"{snippet}\"")
    except json.JSONDecodeError:
        return snippet.replace("\\n", "\n").replace("\\\"", "\"").replace("\\'", "'").strip()


def _coerce_list(items: Any) -> list[str]:
    if items is None:
        return []
    if isinstance(items, list):
        return [str(item) for item in items]
    return [str(items)]


def _filter_instagram_slides(slides: list[str]) -> list[str]:
    filtered = []
    for item in slides:
        cleaned = item.strip()
        if re.match(r"^[\\w./-]+\\.(jpg|jpeg|png|gif|webp)$", cleaned, re.IGNORECASE):
            continue
        filtered.append(cleaned)
    return filtered


def _enabled_pipelines_from_artifacts(artifacts: Dict[str, Any]) -> list[str]:
    options = artifacts.get("options", {}).get("metadata", {})
    fast_mode = bool(options.get("fast_mode"))
    if fast_mode:
        return ["Video", "Social", "SEO", "QA", "Analysis"]
    return ["Video", "Audio", "Social", "Hindi", "SEO", "QA", "Analysis"]


def _render_social_carousel(
    title: str,
    items: list[str],
    job_id: str,
    channel: str,
    copy_text: str,
) -> None:
    share_url = _share_url(channel, copy_text)
    safe_items = [escape(item) for item in items if item]
    slides = "\n".join(
        [
            f"<div class='slide'><div class='slide-inner'>{item}</div></div>"
            for item in safe_items
        ]
    )
    html = f"""
    <style>
      .card {{ border: 1px solid #e2e8f0; border-radius: 18px; padding: 18px; background: linear-gradient(135deg, #f8fafc 0%, #eef2ff 100%); margin-bottom: 18px; max-width: 920px; box-shadow: 0 12px 30px rgba(15,23,42,0.08); }}
      .card h4 {{ margin: 0; font-size: 18px; color: #0f172a; }}
      .carousel {{ display: flex; gap: 12px; overflow-x: auto; scroll-snap-type: x mandatory; padding-bottom: 8px; scroll-behavior: smooth; }}
      .slide {{ scroll-snap-align: center; min-width: 100%; max-width: 100%; background: white; border: 1px solid #e2e8f0; border-radius: 16px; padding: 16px; box-shadow: inset 0 0 0 1px rgba(99,102,241,0.05); }}
      .slide-inner {{ font-size: 14px; line-height: 1.55; color: #0f172a; }}
      .actions {{ display: flex; gap: 10px; margin-top: 12px; align-items: center; }}
      .icon-btn {{ border: 1px solid #e2e8f0; border-radius: 10px; padding: 6px 10px; cursor: pointer; background: white; font-size: 16px; box-shadow: 0 6px 12px rgba(15,23,42,0.08); }}
      .icon-link {{ text-decoration: none; }}
      .title-row {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; }}
      .nav {{ display: flex; gap: 6px; }}
    </style>
    <div class="card">
      <div class="title-row">
        <h4>{escape(title)}</h4>
        <div class="nav">
          <button class="icon-btn" id="prev_{channel}_{job_id}">◀</button>
          <button class="icon-btn" id="next_{channel}_{job_id}">▶</button>
        </div>
      </div>
      <div class="carousel" id="carousel_{channel}_{job_id}">
        {slides}
      </div>
      <div class="actions">
        <button class="icon-btn" id="copy_{channel}_{job_id}">📋</button>
        <a class="icon-link" href="{share_url}" target="_blank"><span class="icon-btn">🔗</span></a>
      </div>
    </div>
    <script>
      const btn = document.getElementById("copy_{channel}_{job_id}");
      const carousel = document.getElementById("carousel_{channel}_{job_id}");
      const prevBtn = document.getElementById("prev_{channel}_{job_id}");
      const nextBtn = document.getElementById("next_{channel}_{job_id}");
      const scrollByCard = () => carousel?.clientWidth || 0;
      prevBtn?.addEventListener("click", () => {{
        carousel.scrollLeft -= scrollByCard();
      }});
      nextBtn?.addEventListener("click", () => {{
        carousel.scrollLeft += scrollByCard();
      }});
      btn.addEventListener("click", () => {{
        navigator.clipboard.writeText({json.dumps(copy_text)});
        btn.textContent = "✅";
        setTimeout(() => (btn.textContent = "📋"), 1200);
      }});
    </script>
    """
    components.html(html, height=340)
    st.download_button(
        "⬇️",
        copy_text.encode("utf-8"),
        file_name=f"{channel}_{job_id}.txt",
        key=f"download_{channel}_{job_id}",
    )


def _copy_button(label: str, text: str, key: str) -> None:
    payload = json.dumps(text)
    html = f"""
    <button id="btn_{key}">{label}</button>
    <script>
    const btn = document.getElementById("btn_{key}");
    btn.addEventListener("click", () => {{
      navigator.clipboard.writeText({payload});
      btn.innerText = "Copied";
      setTimeout(() => (btn.innerText = "{label}"), 1200);
    }});
    </script>
    """
    components.html(html, height=35)


def _share_url(channel: str, text: str) -> str:
    encoded = urllib.parse.quote(text)
    links = {
        "twitter": f"https://twitter.com/intent/tweet?text={encoded}",
        "linkedin": f"https://www.linkedin.com/sharing/share-offsite/?url={encoded}",
        "facebook": f"https://www.facebook.com/sharer/sharer.php?u={encoded}",
        "whatsapp": f"https://wa.me/?text={encoded}",
        "instagram": "https://www.instagram.com/",
    }
    return links.get(channel, "https://www.ht.com")


def _missing_env_keys() -> list[str]:
    required = [
        "ANTHROPIC_API_KEY",
        "DID_API_KEY",
        "DID_SOURCE_URL",
        "ELEVENLABS_API_KEY",
        "ELEVENLABS_VOICE_ID",
        "BRAVE_SEARCH_API_KEY",
    ]
    missing = []
    for key in required:
        if not os.getenv(key):
            missing.append(key)
    return missing


def _auto_refresh(interval_ms: int) -> None:
    if hasattr(st, "autorefresh"):
        st.autorefresh(interval=interval_ms, key="progress_autorefresh")
    else:
        seconds = max(1, int(interval_ms / 1000))
        st.markdown(f"<meta http-equiv='refresh' content='{seconds}'>", unsafe_allow_html=True)


def _demo_mode_enabled() -> bool:
    return os.getenv("DEMO_MODE", "0").lower() in {"1", "true", "yes"}


def _run_demo(job_manager: JobManager) -> None:
    if not DEMO_ARTICLE_PATH.exists():
        st.error("Demo article not found.")
        return
    with DEMO_ARTICLE_PATH.open("r", encoding="utf-8") as handle:
        article_text = handle.read()
    st.info("Demo mode: running with the preset article.")
    job_id = job_manager.create_job()
    job_manager.start_analysis(job_id, "paste", article_text, use_style=True, audience="Markets", fast_mode=False)
    st.session_state.job_id = job_id
    st.session_state.demo_started = True
    st.rerun()


def _use_case_description(use_case: str) -> str:
    descriptions = {
        "Editorial Full Pack": "Full distribution set: video, audio, social, Hindi, SEO, QA.",
        "Breaking News Fast Pack": "Speed mode for spikes: video, social, SEO, QA only.",
        "Markets Pulse": "Finance-first framing with concise market impact.",
        "Youth Summary": "Shorter, punchier social hooks for younger audiences.",
        "Hindi First": "Hindi-led summary and voice for regional reach.",
    }
    return descriptions.get(use_case, "")


def _render_use_case_help() -> None:
    st.markdown(
        """\
**Use-case guide**

- **Editorial Full Pack**: All formats for daily coverage, maximum reach.
- **Breaking News Fast Pack**: Minimal outputs for speed during spikes.
- **Markets Pulse**: Finance-first framing for investors and analysts.
- **Youth Summary**: Shorter hooks for social-native audiences.
- **Hindi First**: Hindi-led reach for regional growth.
"""
    )


def _ensure_use_case_defaults() -> None:
    if "use_case" not in st.session_state:
        st.session_state.use_case = "Editorial Full Pack"
    if "use_style" not in st.session_state:
        st.session_state.use_style = True
    if "fast_mode" not in st.session_state:
        st.session_state.fast_mode = False
    if "audience" not in st.session_state:
        st.session_state.audience = "General"


def _apply_use_case_defaults() -> None:
    use_case = st.session_state.use_case
    if use_case == "Breaking News Fast Pack":
        st.session_state.fast_mode = True
        st.session_state.audience = "General"
    elif use_case == "Markets Pulse":
        st.session_state.fast_mode = False
        st.session_state.audience = "Markets"
    elif use_case == "Youth Summary":
        st.session_state.fast_mode = False
        st.session_state.audience = "Youth"
    elif use_case == "Hindi First":
        st.session_state.fast_mode = False
        st.session_state.audience = "Hindi-first"
    else:
        st.session_state.fast_mode = False
        st.session_state.audience = "General"


def _outputs_for_mode(fast_mode: bool) -> list[str]:
    if fast_mode:
        return ["Video", "Social", "SEO", "QA"]
    return ["Video", "Audio", "Social", "Hindi", "SEO", "QA"]


def _render_publish_pack(artifacts: Dict[str, Any]) -> None:
    package = _build_package_manifest(artifacts)
    if package:
        st.download_button(
            "Export for CMS/Scheduler",
            json.dumps(package, ensure_ascii=True, indent=2).encode("utf-8"),
            file_name="cms_package.json",
        )
    csv_payload = _build_social_csv(artifacts)
    if csv_payload:
        st.download_button(
            "Download Social CSV",
            csv_payload.encode("utf-8"),
            file_name="social_posts.csv",
        )


def _build_package_manifest(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    analysis = artifacts.get("analysis")
    if analysis and os.path.exists(analysis["path"]):
        payload["analysis"] = _safe_json_loads(_read_text(analysis["path"]))
    if "video_script" in artifacts:
        payload["video_script"] = _read_text(artifacts["video_script"]["path"])
    if "social" in artifacts:
        payload["social"] = _safe_json_loads(_read_text(artifacts["social"]["path"]))
    if "seo" in artifacts:
        payload["seo"] = _safe_json_loads(_read_text(artifacts["seo"]["path"]))
    if "translation" in artifacts:
        payload["hindi"] = _read_text(artifacts["translation"]["path"])
    if "qa" in artifacts:
        payload["qa"] = _safe_json_loads(_read_text(artifacts["qa"]["path"]))
    return payload


def _build_social_csv(artifacts: Dict[str, Any]) -> str:
    social = artifacts.get("social")
    if not social or not os.path.exists(social["path"]):
        return ""
    data = json.loads(_read_text(social["path"]))
    rows = ["platform,content"]
    for tweet in data.get("twitter_thread", []):
        tweet_text = str(tweet)
        rows.append(f"twitter,\"{tweet_text.replace('\"', '\"\"')}\"")
    rows.append(f"linkedin,\"{str(data.get('linkedin', '')).replace('\"', '\"\"')}\"")
    instagram = data.get("instagram", {})
    rows.append(f"instagram,\"{str(instagram.get('caption', '')).replace('\"', '\"\"')}\"")
    rows.append(f"facebook,\"{str(data.get('facebook', '')).replace('\"', '\"\"')}\"")
    rows.append(f"whatsapp,\"{str(data.get('whatsapp', '')).replace('\"', '\"\"')}\"")
    return "\n".join(rows) + "\n"


if __name__ == "__main__":
    main()
