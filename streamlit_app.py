import os
from pathlib import Path
import re
from io import BytesIO
from typing import Dict, List

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


def extract_paper_pdf_links(markdown_content: str) -> List[Dict[str, str]]:
    """
    Extract unique PDF URLs from a generated report.

    The report may contain either:
    - Markdown links: [Some title](https://.../paper.pdf)
    - Plain lines: **PDF**: https://.../paper.pdf
    """
    # Keep this function for backwards compatibility, but delegate to
    # the more general `extract_paper_links()` and filter PDFs.
    papers = extract_paper_links(markdown_content)
    return [
        {"title": p.get("title", "Paper"), "url": p.get("url", "")}
        for p in papers
        if str(p.get("is_pdf", "")).lower() == "true"
    ]


def extract_paper_links(markdown_content: str) -> List[Dict[str, str]]:
    """
    Extract paper links from a generated report.

    Supports:
    - Bulleted "Sources" section: • [Title](https://.../paper-or-pdf-url)
    - PDF markers: **PDF**: https://.../paper.pdf

    Returns unique links with `title`, `url`, and `is_pdf`.
    """
    if not markdown_content:
        return []

    found: Dict[str, Dict[str, str]] = {}  # url -> {title,url,is_pdf}

    # Try to narrow extraction to the Sources section to reduce false positives.
    sources_block = None
    m = re.search(
        r"(?ims)\*\*Sources\*\*:\s*(.*?)^\*\*Generation Date\*\*",
        markdown_content,
        flags=re.MULTILINE,
    )
    if m:
        sources_block = m.group(1)
    else:
        sources_block = markdown_content

    # Bullet links: • [Something](https://...)
    bullet_link_pattern = re.compile(
        r"•\s*\[([^\]]+)\]\((https?://[^)\s]+)\)",
        flags=re.IGNORECASE,
    )
    for bm in bullet_link_pattern.finditer(sources_block):
        title = (bm.group(1) or "").strip()
        url = (bm.group(2) or "").strip()
        if not url or not url.lower().startswith("http"):
            continue
        is_pdf = url.lower().split("?", 1)[0].endswith(".pdf")
        found[url] = {"title": title or Path(url).name, "url": url, "is_pdf": str(is_pdf)}

    # Also parse **PDF** lines (common in some reports)
    pdf_line_pattern = re.compile(
        r"\*\*PDF\*\*\s*:\s*(https?://\S+?\.pdf\S*)",
        flags=re.IGNORECASE,
    )
    for pm in pdf_line_pattern.finditer(markdown_content):
        url = (pm.group(1) or "").strip()
        if not url or not url.lower().startswith("http"):
            continue
        if url not in found:
            found[url] = {"title": Path(url.split("?", 1)[0]).name, "url": url, "is_pdf": "True"}

    papers = list(found.values())
    papers.sort(key=lambda x: (x["title"].lower(), x["url"].lower()))
    return papers


def markdown_to_plain_text(markdown_content: str) -> str:
    """
    Best-effort Markdown -> plain text conversion for embedding into a PDF.
    """
    if not markdown_content:
        return ""

    text = markdown_content

    # Remove fenced code blocks if any
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)

    # Convert links [title](url) -> title (url)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", text)

    # Strip images ![alt](url)
    text = re.sub(r"!\[([^\]]*)\]\((https?://[^)]+)\)", r"\1", text)

    # Remove emphasis/bold markers
    text = text.replace("**", "").replace("__", "").replace("*", "").replace("_", "")

    # Remove headings/bullets separators
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.MULTILINE)

    # Remove horizontal rules
    text = re.sub(r"^\s*---\s*$", "", text, flags=re.MULTILINE)

    # Collapse repeated whitespace a bit
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def build_summary_pdf_bytes(markdown_content: str, report_title: str) -> bytes:
    """
    Build a simple PDF from the report text using `reportlab`.

    Returns raw PDF bytes for Streamlit's `st.download_button`.
    """
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase.pdfmetrics import stringWidth
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "PDF generation needs `reportlab`. Install it via `pip install -r requirements.txt`."
        ) from e

    plain = markdown_to_plain_text(markdown_content)
    if not plain:
        plain = "No report content available."

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    margin_x = 48
    margin_y = 48
    line_height = 12

    y = height - margin_y

    def new_page() -> None:
        nonlocal y
        c.showPage()
        y = height - margin_y

    # Title
    c.setFont("Helvetica-Bold", 14)
    c.drawString(margin_x, y, report_title[:120])
    y -= line_height * 1.6
    c.setFont("Helvetica", 10)

    max_width = width - (margin_x * 2)

    def wrap_line(s: str) -> List[str]:
        # Word-wrap based on rendered width
        words = s.split()
        lines: List[str] = []
        cur = ""
        for w in words:
            candidate = f"{cur} {w}".strip()
            if stringWidth(candidate, "Helvetica", 10) <= max_width:
                cur = candidate
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines or [s]

    # Render paragraph-by-paragraph to preserve some spacing
    paragraphs = plain.split("\n\n")
    for para in paragraphs:
        if not para.strip():
            y -= line_height * 0.6
            continue

        wrapped = wrap_line(para.replace("\n", " ").strip())
        for line in wrapped:
            if y < margin_y + line_height:
                new_page()
                c.setFont("Helvetica", 10)
            c.drawString(margin_x, y, line[:1400])
            y -= line_height

        y -= line_height * 0.4

    c.save()
    return buffer.getvalue()


def extract_summary_from_report(markdown_content: str) -> str:
    """
    Extract a concise "summary" section from the report markdown.

    Heuristics:
    - Prefer "## Synthesis and Conclusions" section.
    - Fall back to "## Introduction" section.
    - Otherwise, return the first chunk of the report.
    """
    if not markdown_content:
        return ""

    # Prefer synthesis/conclusions
    m = re.search(
        r"(?ims)^##\s+Synthesis\s+and\s+Conclusions\s*$.*?(?=^##\s+)",
        markdown_content,
    )
    if m:
        # Keep markdown formatting but remove leading/trailing whitespace
        return m.group(0).strip()

    # Fall back to introduction
    m = re.search(
        r"(?ims)^##\s+Introduction\s*$.*?(?=^##\s+|^#\s)",
        markdown_content,
    )
    if m:
        return m.group(0).strip()

    # Final fallback
    return markdown_content.strip()[:1500]


def main():
    st.set_page_config(page_title="SentinelARC Research Dashboard", layout="wide")

    # Gemini-like layout styling.
    # Note: Streamlit is not pixel-identical to Gemini.com, but this makes the UI layout/spacing closer.
    st.markdown(
        """
        <style>
          /* Base */
          html, body { background: #ffffff; color: #0f172a; }

          /* Hide Streamlit top menu/header blocks (if present) */
          #MainMenu { visibility: hidden; }
          footer { visibility: hidden; }

          /* Sidebar */
          section[data-testid="stSidebar"] > div:first-child {
            background: #f3f4f6;
            border-right: 1px solid rgba(15,23,42,0.08);
            padding: 16px 14px;
          }

          .gemSidebarItem{
            font-size: 13px;
            color: rgba(15,23,42,0.75);
            padding: 6px 10px;
            border-radius: 10px;
          }
          .gemSidebarItem:hover{
            background: rgba(255,255,255,0.6);
          }

          /* Center main content area like a chat */
          div[data-testid="stVerticalBlock"] {
            max-width: 980px;
            margin: 0 auto;
          }

          /* Top title */
          .geminiTitleBar {
            display: flex;
            align-items: center;
            justify-content: flex-start;
            padding: 18px 4px 10px 10px;
            max-width: 980px;
            margin: 0 auto;
          }
          .geminiTitleBar h1 {
            font-size: 20px;
            font-weight: 700;
            margin: 0;
          }

          /* Chat bubbles: make them flatter/cleaner */
          .stChatMessage { border-radius: 14px; }
          .stChatMessage .stMarkdown { font-size: 14px; }

          /* Expander header tweak */
          details summary { font-weight: 600; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div style='max-width:980px;margin:0 auto 14px auto;font-size:14px;font-weight:700;'>SentinelARC</div>",
        unsafe_allow_html=True,
    )

    # --- Sidebar: menu (clickable) + report picker with search ---
    selected_path = None
    with st.sidebar:
        st.markdown("#### Menu")
        if st.button("+ New chat", use_container_width=True, key="btn_new_chat"):
            st.session_state["last_query"] = ""
            st.session_state["report_choice"] = ""
            st.rerun()
        if st.button("Scheduled actions", use_container_width=True, key="btn_scheduled"):
            st.session_state["menu_info"] = "Scheduled actions (UI placeholder)"
            st.rerun()
        if st.button("Gems", use_container_width=True, key="btn_gems"):
            st.session_state["menu_info"] = "Gems (UI placeholder)"
            st.rerun()
        if st.button("My stuff", use_container_width=True, key="btn_mystuff"):
            st.session_state["menu_info"] = "My stuff (UI placeholder)"
            st.rerun()

        st.markdown("---")
        st.markdown("#### Chats")

        report_search = st.text_input("Search reports", placeholder="Type to filter...", key="report_search")
        files = list_reports()
        if not files:
            st.info("No reports yet.")
        else:
            all_options = [f.name for f in files]
            if report_search.strip():
                filtered = [o for o in all_options if report_search.lower() in o.lower()]
            else:
                filtered = all_options

            if not filtered:
                st.info("No reports match your search.")
            else:
                if "report_choice" not in st.session_state or st.session_state["report_choice"] not in filtered:
                    st.session_state["report_choice"] = filtered[0]
                choice = st.selectbox(
                    "Report",
                    filtered,
                    index=filtered.index(st.session_state["report_choice"]),
                    key="report_choice",
                    label_visibility="collapsed",
                )
                selected_path = next(p for p in files if p.name == choice)

        if st.button("Refresh reports", use_container_width=True):
            st.rerun()

        if st.session_state.get("menu_info"):
            st.caption(st.session_state["menu_info"])

    # --- Main content (Gemini-like order without chat avatars) ---
    last_query = st.session_state.get("last_query")
    if last_query:
        with st.container(border=True):
            st.markdown("**You**")
            st.markdown(last_query)

    if not selected_path:
        with st.container(border=True):
            st.markdown("**SentinelARC**")
            st.info("Select a report from the sidebar to view summary, paper links, and PDF downloads.")
    else:
        content = read_report(selected_path)
        papers = extract_paper_links(content)
        summary_md = extract_summary_from_report(content)

        with st.container(border=True):
            st.caption(f"Report: `{selected_path.name}`")

            # 1) Summary first
            st.markdown("### Summary")
            if summary_md:
                st.markdown(summary_md)
            else:
                st.info("No summary section detected in this report.")

            # 2) Papers clickable next (show ALL paper links found)
            st.markdown(f"### Papers ({len(papers)})")
            if not papers:
                st.info("No paper links were detected in this report.")
            else:
                for i, p in enumerate(papers, start=1):
                    title = (p.get("title") or "Paper").strip()
                    st.markdown(f"{i}. [{title}]({p['url']})")

            # 3) Summary PDF last
            st.markdown("### Summary PDF")

            cache_key = selected_path.name
            if st.session_state.get("summary_cache_key") != cache_key:
                st.session_state["summary_cache_key"] = cache_key
                st.session_state.pop("summary_pdf_bytes", None)
                st.session_state.pop("summary_pdf_name", None)

            generate_clicked = st.button(
                "Generate Summary PDF",
                help="Creates a PDF from the selected report (best-effort).",
                use_container_width=True,
            )

            if generate_clicked:
                with st.spinner("Generating summary PDF..."):
                    pdf_bytes = build_summary_pdf_bytes(
                        content,
                        report_title=selected_path.name,
                    )
                    st.session_state["summary_pdf_bytes"] = pdf_bytes
                    st.session_state["summary_pdf_name"] = f"summary_{selected_path.stem}.pdf"

            pdf_bytes = st.session_state.get("summary_pdf_bytes")
            pdf_name = st.session_state.get("summary_pdf_name", "summary.pdf")
            if pdf_bytes:
                st.download_button(
                    label="Download Summary PDF",
                    data=pdf_bytes,
                    file_name=pdf_name,
                    mime="application/pdf",
                    use_container_width=True,
                )
            else:
                st.info("Click 'Generate Summary PDF' to enable the download.")

    # --- Search bar / input (bottom) ---
    prompt = st.chat_input("Ask for a new research run (e.g., RAG graph impact)...")
    if prompt:
        with st.spinner("Sending query to orchestrator..."):
            try:
                trigger_research(prompt.strip())
                st.session_state["last_query"] = prompt.strip()
                st.session_state["task_status"] = "Task accepted. Select the newest report when ready."
                st.rerun()
            except Exception as e:
                st.error(f"Failed to start research: {e}")


if __name__ == "__main__":
    main()

