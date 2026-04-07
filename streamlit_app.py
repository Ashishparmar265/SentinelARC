import os
from pathlib import Path
import re
from io import BytesIO
from typing import Dict, List

import requests
import streamlit as st

from src.database import SessionLocal, User, Report, init_db
from src.session_utils import create_session, verify_session, delete_session

# Initialize database tables
init_db()

API_URL = os.getenv("SYNAPSE_API_URL", "http://localhost:8000")
REPORTS_DIR = Path("output/reports")

def show_login_page():
    st.markdown("<h1 style='text-align: center; margin-top: 50px;'>SentinelARC Login</h1>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_login, tab_register = st.tabs(["Login", "Register"])
        
        with tab_login:
            with st.form("login_form"):
                st.subheader("Login")
                username = st.text_input("Username").strip()
                password = st.text_input("Password", type="password")
                remember_me = st.checkbox("Keep me logged in")
                submit = st.form_submit_button("Login", use_container_width=True)
                
                if submit:
                    if not username or not password:
                        st.error("Please enter both username and password.")
                    else:
                        db = SessionLocal()
                        user = db.query(User).filter(User.username == username).first()
                        db.close()
                        if user and user.verify_password(password):
                            st.session_state["authenticated"] = True
                            st.session_state["user_id"] = user.id
                            st.session_state["username"] = user.username
                            
                            if remember_me:
                                token = create_session(user.id)
                                st.query_params["session"] = token
                                
                            st.success("Login successful!")
                            st.rerun()
                        else:
                            st.error("Invalid username or password.")
                            
        with tab_register:
            with st.form("register_form"):
                st.subheader("Create a New Profile")
                reg_username = st.text_input("Choose Username").strip()
                reg_password = st.text_input("Choose Password", type="password")
                reg_submit = st.form_submit_button("Register", use_container_width=True)
                
                if reg_submit:
                    if not reg_username or not reg_password:
                        st.error("Please fill out all fields.")
                    else:
                        db = SessionLocal()
                        existing = db.query(User).filter(User.username == reg_username).first()
                        if existing:
                            st.error("Username already taken. Please choose another.")
                        else:
                            new_user = User(
                                username=reg_username, 
                                password_hash=User.hash_password(reg_password)
                            )
                            db.add(new_user)
                            db.commit()
                            db.refresh(new_user)
                            st.success("Account created! You can now login.")
                        db.close()



def trigger_research(query: str, user_id: int) -> dict:
    """Call the FastAPI /research endpoint."""
    payload = {"query": query, "user_id": user_id}
    # Short connect timeout, no read timeout (request returns immediately anyway)
    resp = requests.post(f"{API_URL}/research", json=payload, timeout=(5, None))
    resp.raise_for_status()
    return resp.json()

def trigger_general_ai(query: str, model: str, chat_history: list, user_id: int):
    """Call the FastAPI /general_chat endpoint with streaming support."""
    payload = {
        "query": query,
        "model": model,
        "history": chat_history,
        "user_id": user_id
    }
    # Initial connection timeout: 10s, no read timeout for streaming
    with requests.post(f"{API_URL}/general_chat", json=payload, stream=True, timeout=(10, None)) as resp:
        resp.raise_for_status()
        for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
            if chunk:
                yield chunk


def list_reports(user_id: int):
    """Return report files sorted by modified time (newest first)."""
    if not user_id:
        return []
        
    user_dir = REPORTS_DIR / str(user_id)
    if not user_dir.exists():
        return []

    files = sorted(
        user_dir.glob("research_report_*.md"),
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
    st.set_page_config(page_title="SentinelARC Research Dashboard", layout="wide", initial_sidebar_state="expanded")

    # Check for existing session in query params
    if not st.session_state.get("authenticated"):
        session_token = st.query_params.get("session")
        if session_token:
            user_info = verify_session(session_token)
            if user_info:
                st.session_state["authenticated"] = True
                st.session_state["user_id"] = user_info["id"]
                st.session_state["username"] = user_info["username"]

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

          /* Sidebar – always visible, never collapsed */
          section[data-testid="stSidebar"] {
            background-color: #ffffff;
            border-right: 1px solid #e2e8f0;
            box-shadow: 2px 0 10px rgba(0,0,0,0.02);
            min-width: 260px !important;
            display: flex !important;
          }
          /* Hide the collapse arrow button */
          button[data-testid="baseButton-secondary"] svg[data-testid="stIconExpander"],
          button[data-testid="collapsedControl"] {
            display: none !important;
          }
          section[data-testid="stSidebar"][aria-expanded="false"] {
            transform: none !important;
            margin-left: 0 !important;
            visibility: visible !important;
            display: flex !important;
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

          /* Main content area – allow independent scroll for sticky to work */
          div[data-testid="stVerticalBlock"] {
            max-width: 1000px;
            margin: 0 auto;
            padding: 0 1rem;
          }

          /* Make sticky work: the scroll must happen inside Streamlit's main content block */
          section.main > div.block-container {
            overflow-y: auto !important;
            height: 100vh !important;
            padding-top: 0 !important;
          }

          /* Control Center sticky wrapper – pin it just below the header */
          div[data-stickytop="control-center"] {
            position: sticky;
            top: 80px;
            z-index: 998;
            background: #f8fafc;
            padding-bottom: 8px;
            margin-bottom: 8px;
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

          /* Sidebar Brand Block – top of left panel */
          .sidebar-brand {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            padding: 18px 16px 14px 16px;
            border-radius: 12px;
            margin-bottom: 4px;
            color: white;
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.2);
          }
          .sidebar-brand h2 {
            color: white !important;
            margin: 0 0 4px 0 !important;
            font-size: 20px !important;
            font-weight: 700 !important;
            letter-spacing: -0.02em;
            border-bottom: none !important;
          }
          .sidebar-brand p {
            margin: 0 0 10px 0;
            color: #94a3b8;
            font-size: 11px;
            line-height: 1.4;
          }
          .sidebar-badge {
            display: inline-block;
            background: rgba(52, 211, 153, 0.2);
            color: #34d399;
            padding: 3px 9px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: 600;
            border: 1px solid rgba(52, 211, 153, 0.3);
          }
          
          /* Control Center Card in Sidebar */
          .sidebar-control-center {
            background-color: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 16px;
            margin-top: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
          }
          .sidebar-control-center h5 {
            margin-top: 0 !important;
            font-size: 14px !important;
            color: #1e293b !important;
            font-weight: 600 !important;
          }
          
          /* Top-Right Profile Rectangle */
          /* Target only the specific vertical block that contains our marker */
          div[data-testid="stVerticalBlock"]:has(div.top-right-profile-marker) {
            position: fixed !important;
            top: 1rem !important;
            right: 1.5rem !important;
            z-index: 10001 !important; /* Higher than everything else */
            background: rgba(255, 255, 255, 0.98) !important;
            backdrop-filter: blur(10px) !important;
            padding: 10px 16px !important; /* Slightly more compact */
            border-radius: 12px !important;
            border: 1px solid #e2e8f0 !important;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1) !important;
            width: auto !important;
            min-width: 140px !important;
            height: auto !important;
          }
          
          /* Main content padding-right to avoid profile overlap */
          .stAppViewMain .block-container {
              padding-right: 200px !important;
              max-width: 98% !important;
          }
          
          /* Fix for small screens / collapsed sidebar */
          @media (max-width: 768px) {
              .stAppViewMain .block-container {
                  padding-right: 1rem !important;
              }
              div[data-testid="stVerticalBlock"]:has(div.top-right-profile-marker) {
                  position: static !important;
                  margin-bottom: 1rem;
                  width: 100% !important;
              }
          }

          /* Ensure widgets inside don't have extra margins */
          div[data-testid="stVerticalBlock"]:has(div.top-right-profile-marker) div[data-testid="stVerticalBlock"] {
              gap: 0.5rem !important;
          }
          .top-right-profile-marker {
              display: none;
          }

        </style>
        """,
        unsafe_allow_html=True,
    )

    # Search Bar Spinner UI (Phase 2: UI Aesthetics)
    if st.session_state.get("is_researching"):
        st.markdown(
            """
            <style>
              /* Target the submit button icon */
              [data-testid="stChatInputSubmit"] svg {
                display: none !important;
              }
              /* Create the rotating ring */
              [data-testid="stChatInputSubmit"]::after {
                content: "";
                display: block;
                width: 18px;
                height: 18px;
                border: 2px solid #cbd5e1;
                border-top-color: #3b82f6;
                border-radius: 50%;
                animation: gear-spin 0.8s linear infinite;
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
              }
              @keyframes gear-spin {
                from { transform: translate(-50%, -50%) rotate(0deg); }
                to { transform: translate(-50%, -50%) rotate(360deg); }
              }
              /* Force visibility and disable interaction while processing */
              [data-testid="stChatInputSubmit"] {
                display: flex !important;
                visibility: visible !important;
                opacity: 1 !important;
                background-color: transparent !important;
                border: none !important;
                pointer-events: none;
              }
            </style>
            """,
            unsafe_allow_html=True
        )


    if not st.session_state.get("authenticated"):
        show_login_page()
        return

    # ── Top-Right Profile Overlay ──────────────────────────────────────
    with st.container():
        # This empty div acts as a marker for our CSS selector
        st.markdown('<div class="top-right-profile-marker"></div>', unsafe_allow_html=True)
        st.markdown(f"👤 **{st.session_state.get('username', 'User')}**")
        
        if st.button("Logout", key="top_right_logout", use_container_width=True):
            session_token = st.query_params.get("session")
            if session_token:
                delete_session(session_token)
                st.query_params.clear()
            for k in ["authenticated", "user_id", "username", "chat_history",
                      "shown_reports", "active_report_id", "_backfilled"]:
                st.session_state.pop(k, None)
            st.rerun()


    # ── helpers ──────────────────────────────────────────────────────────
    user_id = st.session_state.get("user_id")

    def _backfill_reports_from_disk():
        """Scan on-disk report files and register any that are not yet in the DB."""
        from src.database import SessionLocal, Report
        from pathlib import Path as _P
        user_dir = _P("output/reports") / str(user_id)
        if not user_dir.exists():
            return
        db = SessionLocal()
        existing_paths = {r.file_path for r in db.query(Report).filter(Report.user_id == user_id).all()}
        for f in user_dir.glob("research_report_*.md"):
            fp = str(f)
            if fp not in existing_paths:
                new_r = Report(user_id=user_id, file_path=fp, query="(Recovered — query unknown)")
                db.add(new_r)
        db.commit()
        db.close()

    # Run the backfill once per session
    if not st.session_state.get("_backfilled"):
        _backfill_reports_from_disk()
        st.session_state["_backfilled"] = True

    def _load_all_reports():
        from src.database import SessionLocal, Report
        db = SessionLocal()
        rows = (db.query(Report)
                  .filter(Report.user_id == user_id)
                  .order_by(Report.created_at.asc())
                  .all())
        result = [(r.id, r.query, r.file_path) for r in rows]
        db.close()
        return result  # list of (id, query, file_path)

    all_reports = _load_all_reports()

    # ── Left sidebar – Chat History Panel ────────────────────────────────
    with st.sidebar:
        # Brand block at the very top of the sidebar
        st.markdown("""
        <div class="sidebar-brand">
            <h2>SentinelARC</h2>
            <p>Autonomous Literature Review &amp; Fact-Checking</p>
            <span class="sidebar-badge">● System Online</span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")
        if st.button("＋ New Research", use_container_width=True, key="btn_new_chat",
                     type="primary"):
            st.session_state["active_report_id"] = None
            st.session_state["chat_history"] = []
            st.rerun()

        st.markdown("#### 🗂 Chat History")
        if not all_reports:
            st.caption("No chats yet. Start your first research!")
        else:
            search_q = st.text_input("", placeholder="🔍 Filter chats…", label_visibility="collapsed", key="chat_search")
            for rep_id, query, fpath in reversed(all_reports):  # newest first
                label = (query.split()[0] if query.split() else "Chat")  # first word
                if search_q and search_q.lower() not in query.lower():
                    continue
                full_label = f"**{label}** — _{query[:35]}{'…' if len(query)>35 else ''}_"
                is_active = st.session_state.get("active_report_id") == rep_id
                btn_style = "primary" if is_active else "secondary"
                if st.button(full_label, key=f"chat_{rep_id}", use_container_width=True, type=btn_style):
                    # Open this chat: set active, rebuild history for this single chat
                    st.session_state["active_report_id"] = rep_id
                    st.session_state["chat_history"] = [
                        {"type": "user",   "content": f"Research: {query}"},
                        {"type": "report", "path":    fpath}
                    ]
                    st.session_state["shown_reports"] = {fpath}
                    st.rerun()

        # --- Sidebar Control Center (at bottom) ---
        st.markdown("---")
        with st.container(border=True):
            st.markdown("##### 🛠️ Control Center")
            
            # Restore mode from query params on page refresh
            if "mode" not in st.session_state:
                saved_mode = st.query_params.get("mode", "research")
                st.session_state["mode"] = "General AI" if saved_mode == "general" else "Research AI"
                
            current_is_general = st.session_state.get("mode") == "General AI"
            mode = st.radio("**Intelligence Mode**", ["Research AI", "General AI"],
                            index=1 if current_is_general else 0,
                            key="sidebar_mode_toggle")
            
            new_mode = "General AI" if "General AI" in mode else "Research AI"
            if new_mode != st.session_state.get("mode"):
                st.session_state["mode"] = new_mode
                st.query_params["mode"] = "general" if new_mode == "General AI" else "research"
                st.rerun()
                
            if st.session_state.get("mode") == "General AI":
                st.session_state["ai_model"] = st.selectbox("**Model Selection**", ["llama3.1:8b", "mistral", "qwen2.5-coder"])
            else:
                st.caption("Swarm Analysis: Llama 3.k + Qwen 1.5B (Fast Path)")



    # --- Main content: Chat History Management ---
    if "chat_history" not in st.session_state:
        # On first load (no active chat) show all reports in one stream
        st.session_state["chat_history"] = []
        for rep_id, query, fpath in all_reports:
            st.session_state["chat_history"].append({"type": "user",   "content": f"Research: {query}"})
            st.session_state["chat_history"].append({"type": "report", "path":    fpath})

    if "shown_reports" not in st.session_state:
        st.session_state["shown_reports"] = {item.get("path") for item in st.session_state["chat_history"] if item.get("path")}

    # On refresh: check if a research task was in-progress by comparing
    # existing DB record count vs shown_reports — if there are fewer DB rows
    # than shown_reports it means we're mid-task, so restore the spinner.
    if not st.session_state.get("is_researching"):
        # Check if there's an active research task (a query marker file)
        import glob
        task_file = f"output/active_task_{user_id}.flag"
        if os.path.exists(task_file):
            st.session_state["is_researching"] = True
            st.session_state["poll_count"] = 0


    # Auto-detect freshly completed reports from the DB and append to current view
    new_report_found = False
    for rep_id, query, fpath in all_reports:
        if fpath not in st.session_state["shown_reports"]:
            st.session_state["chat_history"].append({"type": "user",   "content": f"Research: {query}"})
            st.session_state["chat_history"].append({"type": "report", "path":    fpath})
            st.session_state["shown_reports"].add(fpath)
            new_report_found = True
            if st.session_state.get("is_researching"):
                st.session_state["is_researching"] = False
                # Clean up the persisted flag file when research completes
                task_flag = f"output/active_task_{user_id}.flag"
                if os.path.exists(task_flag):
                    os.remove(task_flag)
                st.toast("✅ Research complete! Report added below.")

    if new_report_found:
        st.rerun()

    # Render history
    for idx, item in enumerate(st.session_state["chat_history"]):
        if item["type"] == "user":
            with st.chat_message("user"):
                st.markdown(item["content"])
                
        elif item["type"] == "assistant":
            with st.chat_message("assistant"):
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
                if st.session_state["poll_count"] > 900: # Timeout after 30 minutes
                    st.session_state["is_researching"] = False
                    st.error("Request timed out. Check terminal logs.")
                st.rerun()

    # --- Search bar / input (bottom) ---
    prompt = st.chat_input("Message SentinelARC...")
    if prompt:
        # Add user message to history immediately so it appears before the spinner
        st.session_state["chat_history"].append({"type": "user", "content": prompt.strip()})

        if st.session_state.get("mode") == "General AI":
            try:
                with st.chat_message("assistant"):
                    full_response = st.write_stream(trigger_general_ai(
                        prompt.strip(),
                        st.session_state.get("ai_model", "llama3.1:8b"),
                        st.session_state["chat_history"],
                        st.session_state.get("user_id")
                    ))
                st.session_state["chat_history"].append({"type": "assistant", "content": full_response})
                st.rerun()
            except Exception as e:
                st.error(f"General AI request failed: {e}")
        else:
            if st.session_state.get("is_researching"):
                st.warning("Please wait for the current research to finish!")
            else:
                try:
                    # Set spinner flag FIRST, then call API, then rerun → spinner appears immediately
                    st.session_state["is_researching"] = True
                    st.session_state["poll_count"] = 0
                    st.session_state["pending_query"] = prompt.strip()
                    st.rerun()  # This rerun shows the spinner before the API call blocks
                except Exception as e:
                    st.session_state["is_researching"] = False
                    st.error(f"Failed to start research: {e}")

    # Handle the deferred API call for research (set in the block above on previous rerun)
    if st.session_state.get("is_researching") and st.session_state.get("pending_query"):
        pending = st.session_state.pop("pending_query", None)
        if pending:
            try:
                trigger_research(pending, user_id)
                # Write a persistent flag so the spinner can survive a page refresh
                os.makedirs("output", exist_ok=True)
                with open(f"output/active_task_{user_id}.flag", "w") as _f:
                    _f.write(pending)
                st.toast("🔬 Agents are researching... results will appear automatically.")
            except Exception as e:
                st.session_state["is_researching"] = False
                st.error(f"Failed to start research: {e}")


if __name__ == "__main__":
    main()

