import json
import os
from pathlib import Path
from typing import Any, Dict

import streamlit as st

from app.core.job_manager import JobManager
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
    st.title("HT Content Multiplier")
    st.caption("Transform one article into 15+ content pieces in under 2 minutes.")

    job_manager = JobManager()

    if "job_id" not in st.session_state:
        st.session_state.job_id = None
    if st.session_state.job_id:
        _render_progress(job_manager)
        return

    _render_input(job_manager)


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

    if job.status in {"running", "queued"}:
        st.caption("Live updates every second.")
        st.markdown("<meta http-equiv='refresh' content='1'>", unsafe_allow_html=True)

    if job.status == "failed":
        st.error(job.error or "Unknown error")
        if st.button("Start New Job"):
            st.session_state.job_id = None
            st.experimental_rerun()
        return

    if job.status == "completed":
        st.success("Content analysis complete.")
        _render_analysis(job_manager, job_id)
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


def _render_analysis(job_manager: JobManager, job_id: str) -> None:
    artifacts = job_manager.list_artifacts(job_id)
    analysis_path = None
    metadata: Dict[str, Any] = {}
    for artifact in artifacts:
        if artifact["type"] == "analysis":
            analysis_path = artifact["path"]
            metadata = artifact.get("metadata", {})
            break

    if not analysis_path or not os.path.exists(analysis_path):
        st.warning("Analysis artifact not found.")
        return

    with open(analysis_path, "r", encoding="utf-8") as handle:
        analysis_payload = json.load(handle)

    st.subheader("Structured Analysis")
    st.json(analysis_payload)
    if metadata:
        st.caption(f"Model: {metadata.get('model')} | Cost (USD): {metadata.get('cost_usd')}")


if __name__ == "__main__":
    main()
