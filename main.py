import json
import os
from pathlib import Path
from typing import Any, Dict

import streamlit as st

from app.core.job_manager import JobManager
from app.utils.archive import build_zip
from app.utils.validation import ValidationError, validate_article

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


ROOT_DIR = Path(__file__).parent
DEFAULT_TITLE = "HT Content Multiplier"


def main() -> None:
    st.set_page_config(page_title=DEFAULT_TITLE, layout="wide")
    _render_header()

    job_manager = JobManager()

    if "job_id" not in st.session_state:
        st.session_state.job_id = None
    if st.session_state.job_id:
        _render_progress(job_manager)
        return

    _render_input(job_manager)


def _render_header() -> None:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("HT Content Multiplier")
        st.caption("Transform one article into 15+ content pieces in under 2 minutes.")
    with col2:
        st.metric("Target Speed", "2 min", "300x faster")
    _render_sidebar()


def _render_sidebar() -> None:
    st.sidebar.header("System Status")
    missing = _missing_env_keys()
    if missing:
        st.sidebar.warning(f"Missing keys: {', '.join(missing)}")
    else:
        st.sidebar.success("All API keys configured.")
    st.sidebar.info("Pipelines run in parallel with retries and cost tracking.")


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

    with tabs[2]:
        uploaded = st.file_uploader("Upload a .txt file", type=["txt"])
        upload_text = ""
        if uploaded is not None:
            upload_text = uploaded.read().decode("utf-8", errors="ignore")

    st.write("Options")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.checkbox("Video", value=True, disabled=True)
    with col2:
        st.checkbox("Audio", value=True, disabled=True)
    with col3:
        st.checkbox("Social", value=True, disabled=True)
    with col4:
        st.checkbox("Hindi", value=True, disabled=True)

    if st.button("Generate Content Package", type="primary"):
        try:
            source_type, source_payload = _select_source(paste_text, url_text, upload_text)
            if source_type == "paste":
                validate_article(source_payload)
            job_id = job_manager.create_job()
            job_manager.start_analysis(job_id, source_type, source_payload)
            st.session_state.job_id = job_id
            st.experimental_rerun()
        except ValidationError as exc:
            st.error(str(exc))
        except ValueError as exc:
            st.error(str(exc))


def _render_progress(job_manager: JobManager) -> None:
    job_id = st.session_state.job_id
    if not job_id:
        return

    job = job_manager.get_job(job_id)
    if not job:
        st.error("Job not found. Please start again.")
        st.session_state.job_id = None
        return

    st.subheader("Generating Content Package")
    st.progress(job.progress)
    st.write(f"Status: {job.status}")
    _render_progress_steps(job_manager, job_id)

    if job.status in {"running", "queued", "generating"}:
        st.caption("Live updates every second.")
        st.markdown("<meta http-equiv='refresh' content='1'>", unsafe_allow_html=True)

    if job.status == "failed":
        st.error(job.error or "Unknown error")
        if st.button("Start New Job"):
            st.session_state.job_id = None
            st.experimental_rerun()
        return

    if job.status in {"completed", "completed_with_errors"}:
        if job.status == "completed_with_errors":
            st.warning(job.error or "Completed with errors.")
        else:
            st.success("Content package ready.")
        _render_dashboard(job_manager, job_id)
        if st.button("Start New Job"):
            st.session_state.job_id = None
            st.experimental_rerun()


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

    tabs = st.tabs(["Video", "Audio", "Social", "Hindi", "SEO", "QA", "Analysis"])
    with tabs[0]:
        _render_video_tab(artifacts_by_type)
    with tabs[1]:
        _render_audio_tab(artifacts_by_type)
    with tabs[2]:
        _render_social_tab(artifacts_by_type)
    with tabs[3]:
        _render_hindi_tab(artifacts_by_type)
    with tabs[4]:
        _render_seo_tab(artifacts_by_type)
    with tabs[5]:
        _render_qa_tab(artifacts_by_type)
    with tabs[6]:
        _render_analysis_tab(artifacts_by_type)


def _render_progress_steps(job_manager: JobManager, job_id: str) -> None:
    artifacts = job_manager.list_artifacts(job_id)
    types = {artifact["type"] for artifact in artifacts}
    error_types = {artifact["type"] for artifact in artifacts if artifact["type"].startswith("error_")}
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
        if error_type in error_types:
            status = "failed"
        elif types.intersection(artifact_types):
            status = "done"
        else:
            status = "pending"
        st.write(f"{label}: {status}")


def _render_video_tab(artifacts: Dict[str, Any]) -> None:
    video = artifacts.get("video_branded") or artifacts.get("video_raw")
    if not video:
        st.info("Video not available yet.")
        return
    st.video(video["path"])
    st.download_button("Download Video", _read_bytes(video["path"]), file_name=os.path.basename(video["path"]))
    script = artifacts.get("video_script")
    if script:
        with open(script["path"], "r", encoding="utf-8") as handle:
            st.text(handle.read())


def _render_audio_tab(artifacts: Dict[str, Any]) -> None:
    audio = artifacts.get("audio")
    if not audio:
        st.info("Audio not available yet.")
        return
    st.audio(audio["path"])
    st.download_button("Download Audio", _read_bytes(audio["path"]), file_name=os.path.basename(audio["path"]))
    audiogram = artifacts.get("audiogram")
    if audiogram and audiogram["path"].endswith(".mp4"):
        st.video(audiogram["path"])


def _render_social_tab(artifacts: Dict[str, Any]) -> None:
    social = artifacts.get("social")
    if not social:
        st.info("Social posts not available yet.")
        return
    with open(social["path"], "r", encoding="utf-8") as handle:
        st.json(json.load(handle))
    st.download_button(
        "Download Social JSON",
        _read_bytes(social["path"]),
        file_name=os.path.basename(social["path"]),
    )


def _render_hindi_tab(artifacts: Dict[str, Any]) -> None:
    translation = artifacts.get("translation")
    if not translation:
        st.info("Hindi translation not available yet.")
        return
    with open(translation["path"], "r", encoding="utf-8") as handle:
        st.text(handle.read())
    st.download_button(
        "Download Hindi",
        _read_bytes(translation["path"]),
        file_name=os.path.basename(translation["path"]),
    )
    voiceover = artifacts.get("translation_audio")
    if voiceover and voiceover["path"].endswith(".mp3"):
        st.audio(voiceover["path"])


def _render_seo_tab(artifacts: Dict[str, Any]) -> None:
    seo = artifacts.get("seo")
    if not seo:
        st.info("SEO package not available yet.")
        return
    with open(seo["path"], "r", encoding="utf-8") as handle:
        st.json(json.load(handle))
    st.download_button("Download SEO JSON", _read_bytes(seo["path"]), file_name=os.path.basename(seo["path"]))


def _render_qa_tab(artifacts: Dict[str, Any]) -> None:
    qa = artifacts.get("qa")
    if not qa:
        st.info("QA report not available yet.")
        return
    with open(qa["path"], "r", encoding="utf-8") as handle:
        st.json(json.load(handle))
    st.download_button("Download QA JSON", _read_bytes(qa["path"]), file_name=os.path.basename(qa["path"]))


def _render_analysis_tab(artifacts: Dict[str, Any]) -> None:
    analysis = artifacts.get("analysis")
    if not analysis:
        st.info("Analysis not available.")
        return
    with open(analysis["path"], "r", encoding="utf-8") as handle:
        st.json(json.load(handle))
    metadata = analysis.get("metadata", {})
    if metadata:
        st.caption(f"Model: {metadata.get('model')} | Cost (USD): {metadata.get('cost_usd')}")


def _read_bytes(path: str) -> bytes:
    if not os.path.exists(path):
        return b""
    with open(path, "rb") as handle:
        return handle.read()


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


if __name__ == "__main__":
    main()
