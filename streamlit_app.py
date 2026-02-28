import os
from pathlib import Path

import requests
import streamlit as st


API_URL = os.getenv("SYNAPSE_API_URL", "http://localhost:8000")
REPORTS_DIR = Path("output/reports")


def trigger_research(query: str) -> dict:
    """Call the FastAPI /research endpoint."""
    payload = {"query": query}
    # Short connect timeout, no read timeout (request returns immediately anyway)
    resp = requests.post(f"{API_URL}/research", json=payload, timeout=(5, None))
    resp.raise_for_status()
    return resp.json()


def list_reports():
    """Return report files sorted by modified time (newest first)."""
    if not REPORTS_DIR.exists():
        return []

    files = sorted(
        REPORTS_DIR.glob("research_report_*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files


def read_report(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Failed to read report: {e}"


def main():
    st.set_page_config(page_title="SentinelARC Research Dashboard", layout="wide")

    st.title("SentinelARC Research Dashboard")
    st.write(
        "Enter a research query, send it to the agent swarm running in Docker "
        "on `http://localhost:8000`, then browse generated Markdown reports "
        "from `output/reports`."
    )

    with st.form("research_form"):
        query = st.text_area(
            "Research query",
            placeholder="e.g. AI in higher education",
            height=100,
        )
        submitted = st.form_submit_button("Start research")

    if submitted:
        if not query.strip():
            st.warning("Please enter a non-empty query.")
        else:
            with st.spinner("Sending query to orchestrator..."):
                try:
                    result = trigger_research(query.strip())
                    st.success(
                        f"Research task accepted. Query: {result.get('query')!r}"
                    )
                except Exception as e:
                    st.error(f"Failed to start research: {e}")

    st.markdown("---")
    st.subheader("Generated Reports")

    files = list_reports()
    if not files:
        st.info(
            "No reports found yet. After running a query and waiting for the "
            "pipeline to finish, refresh this page."
        )
        return

    latest = files[0]
    options = [f.name for f in files]
    choice = st.selectbox("Select report", options, index=0)

    selected_path = next(p for p in files if p.name == choice)
    content = read_report(selected_path)

    st.caption(f"Path: {selected_path}")
    st.text_area("Report content", content, height=500)

    st.download_button(
        label="Download report as .md",
        data=content,
        file_name=selected_path.name,
        mime="text/markdown",
    )


if __name__ == "__main__":
    main()

