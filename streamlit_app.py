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

    # Modern Professional SaaS Styling
    st.markdown(
        """
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
          
          /* Base */
          html, body, [class*="css"] { 
            font-family: 'Inter', sans-serif !important;
            background-color: #f8fafc; 
            color: #0f172a; 
          }

          /* Hide Streamlit top menu/header blocks */
          #MainMenu { visibility: hidden; }
          footer { visibility: hidden; }
          header { visibility: hidden; }

          /* Sidebar */
          section[data-testid="stSidebar"] {
            background-color: #ffffff;
            border-right: 1px solid #e2e8f0;
            box-shadow: 2px 0 10px rgba(0,0,0,0.02);
          }
          section[data-testid="stSidebar"] > div:first-child {
            padding: 24px 16px;
          }
          
          /* Sidebar Buttons */
          div[data-testid="stSidebar"] button {
            background-color: transparent;
            border: 1px solid transparent;
            color: #475569;
            font-weight: 500;
            border-radius: 8px;
            padding: 8px 16px;
            transition: all 0.2s ease;
            text-align: left;
          }
          div[data-testid="stSidebar"] button:hover {
            background-color: #f1f5f9;
            color: #0f172a;
            border-color: #cbd5e1;
          }

          /* Main content area */
          div[data-testid="stVerticalBlock"] {
            max-width: 1000px;
            margin: 0 auto;
            padding: 0 1rem;
          }

          /* Containers / Cards */
          div[data-testid="stVerticalBlock"] > div > div[data-testid="stVerticalBlockBorderWrapper"] {
            background: #ffffff;
            border-radius: 16px;
            border: 1px solid #e2e8f0;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
            padding: 24px;
            margin-bottom: 24px;
            transition: box-shadow 0.3s ease, transform 0.3s ease;
          }
          div[data-testid="stVerticalBlockBorderWrapper"]:hover {
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -4px rgba(0, 0, 0, 0.05);
            transform: translateY(-2px);
          }

          /* Primary Buttons */
          button[kind="primary"] {
            background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            padding: 10px 20px;
            box-shadow: 0 4px 6px rgba(37, 99, 235, 0.2);
            transition: all 0.2s;
          }
          button[kind="primary"]:hover {
            background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
            box-shadow: 0 6px 8px rgba(37, 99, 235, 0.3);
            transform: translateY(-1px);
          }
          
          /* Headers & Typography */
          h1, h2, h3 { color: #0f172a !important; letter-spacing: -0.02em; }
          h3 { font-size: 1.25rem; margin-bottom: 1rem; color: #1e293b; border-bottom: 2px solid #f1f5f9; padding-bottom: 0.5rem; }
          
          /* Chat Input */
          div[data-testid="stChatInput"] {
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.05);
            border: 1px solid #cbd5e1;
            transition: all 0.3s;
          }
          div[data-testid="stChatInput"]:focus-within {
            box-shadow: 0 4px 20px rgba(59, 130, 246, 0.15);
            border-color: #3b82f6;
          }

          /* Top Header Styling */
          .app-header {
            background: linear-gradient(90deg, #1e293b 0%, #0f172a 100%);
            padding: 28px 32px;
            border-radius: 16px;
            margin-bottom: 32px;
            color: white;
            box-shadow: 0 10px 25px rgba(15, 23, 42, 0.15);
            display: flex;
            align-items: center;
            justify-content: space-between;
          }
          .app-header h1 {
            color: white !important;
            margin: 0;
            font-size: 28px;
            font-weight: 700;
            letter-spacing: -0.025em;
          }
          .app-header p {
            margin: 4px 0 0 0;
            color: #94a3b8;
            font-size: 15px;
          }
          .status-badge {
            background: rgba(52, 211, 153, 0.2);
            color: #34d399;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
            border: 1px solid rgba(52, 211, 153, 0.3);
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '''
        <div class="app-header">
            <div>
                <h1>SentinelARC</h1>
                <p>Autonomous Literature Review & Fact-Checking</p>
            </div>
            <div class="status-badge">● System Online</div>
        </div>
        ''',
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
                def on_report_select():
                    st.session_state["report_clicked"] = True

                choice = st.selectbox(
                    "Report",
                    filtered,
                    index=filtered.index(st.session_state["report_choice"]),
                    key="report_choice",
                    label_visibility="collapsed",
                    on_change=on_report_select
                )
                selected_path = next(p for p in files if p.name == choice)

        if st.button("Refresh reports", use_container_width=True):
            st.rerun()

        if st.session_state.get("menu_info"):
            st.caption(st.session_state["menu_info"])

    # --- Main content (Continuous Chat Flow) ---
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    if "shown_reports" not in st.session_state:
        st.session_state["shown_reports"] = set()

    # Track reports that have been shown in history so we can auto-append new ones
    current_files = list_reports()
    
    # Check for newly generated reports (backend saves them to disk async)
    for f in current_files:
        path_str = str(f)
        if path_str not in st.session_state["shown_reports"]:
            # If there's an active query waiting for a report, or if it's just a fresh run newly seen
            # we append it. We'll mark it shown so it only appends once.
            st.session_state["chat_history"].append({"type": "report", "path": path_str})
            st.session_state["shown_reports"].add(path_str)
            if st.session_state.get("is_researching"):
                st.session_state["is_researching"] = False

    # Allow clicking in the sidebar to manually append an old report to the end
    # We use a unique session state flag to detect if it's a genuine click vs a default value rerun
    if "report_clicked" in st.session_state and st.session_state["report_clicked"]:
        if selected_path:
            path_str = str(selected_path)
            if not st.session_state["chat_history"] or st.session_state["chat_history"][-1].get("path") != path_str:
                st.session_state["chat_history"].append({"type": "report", "path": path_str})
        st.session_state["report_clicked"] = False

    # Render history
    for idx, item in enumerate(st.session_state["chat_history"]):
        if item["type"] == "user":
            with st.chat_message("user"):
                st.markdown(item["content"])
        
        elif item["type"] == "report":
            path = Path(item["path"])
            if path.exists():
                content = read_report(path)
                papers = extract_paper_links(content)
                summary_md = extract_summary_from_report(content)
                
                with st.chat_message("assistant"):
                    with st.container(border=True):
                        st.caption(f"Research Report: {path.name}")
                        if summary_md:
                            st.markdown(summary_md)
                        
                        if papers:
                            # User requested maximum 5, minimum 2 papers (the agent returns 5-10 usually)
                            display_papers = papers[:5]
                            st.markdown("---")
                            st.markdown(f"**Sources Found ({len(display_papers)})**")
                            # Direct paper links for the user
                            for p in display_papers:
                                st.markdown(f"• [{p.get('title', 'Paper')}]({p['url']})")
                        
                        # In-card actions
                        col1, col2 = st.columns([1, 1])
                        with col1:
                            if st.button(f"Generate PDF", key=f"gen_{idx}", use_container_width=True):
                                pdf_bytes = build_summary_pdf_bytes(content, report_title=path.name)
                                st.session_state[f"pdf_{idx}"] = pdf_bytes
                                st.rerun()
                        
                        with col2:
                            pdf_bytes = st.session_state.get(f"pdf_{idx}")
                            if pdf_bytes:
                                st.download_button(
                                    "Download Analysis PDF",
                                    data=pdf_bytes,
                                    file_name=f"analysis_{path.stem}.pdf",
                                    mime="application/pdf",
                                    key=f"dl_{idx}",
                                    use_container_width=True
                                )
            else:
                with st.chat_message("assistant"):
                    st.warning(f"Report file `{path.name}` not found or still generating...")


    if st.session_state.get("is_researching"):
        with st.chat_message("assistant"):
            with st.spinner("Researching in background (fetching and synthesizing sources)..."):
                import time
                time.sleep(2)
                st.session_state["poll_count"] = st.session_state.get("poll_count", 0) + 1
                if st.session_state["poll_count"] > 180: # Timeout after 6 minutes
                    st.session_state["is_researching"] = False
                    st.error("Request timed out. Check terminal logs.")
                st.rerun()

    # --- Search bar / input (bottom) ---
    prompt = st.chat_input("Ask for a new research run (e.g., RAG graph impact)...")
    if prompt:
        if st.session_state.get("is_researching"):
            st.warning("Please wait for the current research to finish!")
        else:
            try:
                # Add user message to history
                st.session_state["chat_history"].append({"type": "user", "content": prompt.strip()})
                
                resp = trigger_research(prompt.strip())
                st.toast("Agents are researching... check back in a moment.")
                st.session_state["is_researching"] = True
                st.session_state["poll_count"] = 0
                st.rerun()
            except Exception as e:
                st.error(f"Failed to start research: {e}")


if __name__ == "__main__":
    main()

