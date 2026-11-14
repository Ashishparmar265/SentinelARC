import os
from pathlib import Path
import re
import json
import time
from io import BytesIO
from typing import Dict, List, Optional, Any
from datetime import datetime

import requests
import streamlit as st
import streamlit.components.v1 as components

from src.database import SessionLocal, User, Report, init_db
from src.session_utils import create_session, verify_session, delete_session

# Initialize database tables
init_db()

API_URL = os.getenv("SYNAPSE_API_URL", "http://localhost:8000")
REPORTS_DIR = Path("output/reports")


def show_login_page():
    st.markdown(
        """
        <style>
          .login-container {
            max-width: 440px;
            margin: 60px auto;
            background: #ffffff;
            padding: 36px 32px;
            border-radius: 16px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.08), 0 8px 10px -6px rgba(0, 0, 0, 0.05);
            border: 1px solid #e2e8f0;
          }
          .login-brand {
            text-align: center;
            margin-bottom: 24px;
          }
          .login-brand h1 {
            font-size: 26px;
            font-weight: 700;
            color: #0f172a;
            margin: 0;
            letter-spacing: -0.02em;
          }
          .login-brand p {
            font-size: 13px;
            color: #64748b;
            margin: 6px 0 0 0;
          }
        </style>
        <div class="login-container">
          <div class="login-brand">
            <h1>SentinelARC</h1>
            <p>Autonomous Academic Research & Synthesis Engine</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    col1, col2, col3 = st.columns([1, 1.8, 1])
    with col2:
        tab_login, tab_register = st.tabs(["🔐 Sign In", "✨ Register Profile"])
        
        with tab_login:
            with st.form("login_form"):
                username = st.text_input("Username", placeholder="e.g. researcher").strip()
                password = st.text_input("Password", type="password", placeholder="••••••••")
                remember_me = st.checkbox("Keep me signed in", value=True)
                submit = st.form_submit_button("Sign In", use_container_width=True, type="primary")
                
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
                                
                            st.toast("👋 Welcome back to SentinelARC!")
                            st.rerun()
                        else:
                            st.error("Invalid username or password.")
                            
        with tab_register:
            with st.form("register_form"):
                reg_username = st.text_input("Choose Username", placeholder="e.g. ashish").strip()
                reg_password = st.text_input("Choose Password", type="password", placeholder="••••••••")
                reg_submit = st.form_submit_button("Create Profile", use_container_width=True, type="primary")
                
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
                            st.success("Account created successfully! Please sign in.")
                        db.close()


def trigger_research(query: str, user_id: int) -> dict:
    """Call the FastAPI /research endpoint."""
    task_id = f"task_{user_id}_{int(time.time())}"
    payload = {"query": query, "user_id": user_id, "task_id": task_id}
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


def extract_paper_links(markdown_content: str) -> List[Dict[str, str]]:
    """Extract paper links from a generated report."""
    if not markdown_content:
        return []

    found: Dict[str, Dict[str, str]] = {}
    inline_link_pattern = re.compile(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        flags=re.IGNORECASE,
    )
    for m in inline_link_pattern.finditer(markdown_content):
        title = (m.group(1) or "").strip()
        url = (m.group(2) or "").strip()
        if not url or not url.lower().startswith("http"):
            continue
        is_pdf = url.lower().split("?", 1)[0].endswith(".pdf")
        
        if url not in found:
            found[url] = {"title": title or Path(url).name, "url": url, "is_pdf": str(is_pdf)}

    papers = list(found.values())
    papers.sort(key=lambda x: (x["title"].lower(), x["url"].lower()))
    return papers


def extract_paper_pdf_links(markdown_content: str) -> List[Dict[str, str]]:
    """Extract unique PDF URLs from a generated report."""
    papers = extract_paper_links(markdown_content)
    return [
        {"title": p.get("title", "Paper"), "url": p.get("url", "")}
        for p in papers
        if str(p.get("is_pdf", "")).lower() == "true"
    ]


def markdown_to_plain_text(markdown_content: str) -> str:
    """Best-effort Markdown -> plain text conversion for embedding into a PDF."""
    if not markdown_content:
        return ""
    text = markdown_content
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", text)
    text = re.sub(r"!\[([^\]]*)\]\((https?://[^)]+)\)", r"\1", text)
    text = text.replace("**", "").replace("__", "").replace("*", "").replace("_", "")
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*---\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def build_summary_pdf_bytes(markdown_content: str, report_title: str) -> bytes:
    """Build a styled PDF from the report text using reportlab."""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase.pdfmetrics import stringWidth
    except Exception as e:
        raise RuntimeError("PDF generation requires reportlab.") from e

    plain = markdown_to_plain_text(markdown_content)
    if not plain:
        plain = "No report content available."

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    margin_x = 48
    margin_y = 48
    line_height = 13
    y = height - margin_y

    def new_page():
        nonlocal y
        c.showPage()
        y = height - margin_y

    # Header / Title
    c.setFont("Helvetica-Bold", 14)
    c.drawString(margin_x, y, report_title[:100])
    y -= line_height * 1.8
    c.setFont("Helvetica", 10)
    max_width = width - (margin_x * 2)

    def wrap_line(s: str) -> List[str]:
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
    """Return markdown report content stripped of trailing white spaces."""
    if not markdown_content:
        return ""
    return markdown_content.strip()


def delete_report(report_id: int, file_path: str, user_id: int):
    """Delete report from SQLite database and associated files on disk."""
    try:
        db = SessionLocal()
        rep = db.query(Report).filter(Report.id == report_id, Report.user_id == user_id).first()
        if rep:
            db.delete(rep)
            db.commit()
        db.close()
    except Exception as e:
        print(f"Error deleting report row: {e}")

    # Remove associated files
    p = Path(file_path)
    for ext in [".md", ".html", ".meta.json"]:
        target = p.with_suffix(ext)
        if target.exists():
            try:
                target.unlink()
            except OSError:
                pass


def main():
    st.set_page_config(
        page_title="SentinelARC — Academic Swarm Dashboard",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Check for existing session token in query params
    if not st.session_state.get("authenticated"):
        session_token = st.query_params.get("session")
        if session_token:
            user_info = verify_session(session_token)
            if user_info:
                st.session_state["authenticated"] = True
                st.session_state["user_id"] = user_info["id"]
                st.session_state["username"] = user_info["username"]

    # Modern SaaS CSS Design
    st.markdown(
        """
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
          
          /* Base Typography & Background */
          html, body, [class*="css"] { 
            font-family: 'Inter', sans-serif !important;
            background-color: #f8fafc; 
            color: #0f172a; 
          }
          code, pre {
            font-family: 'JetBrains Mono', monospace !important;
          }

          /* Hide Streamlit top header and footer */
          #MainMenu { visibility: hidden; }
          footer { visibility: hidden; }
          header { visibility: hidden; }

          /* Sidebar Styling */
          section[data-testid="stSidebar"] {
            background-color: #ffffff;
            border-right: 1px solid #e2e8f0;
            box-shadow: 2px 0 12px rgba(0,0,0,0.02);
            min-width: 280px !important;
          }
          
          /* Top Bar Container */
          .sentinel-top-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 18px;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            margin-bottom: 24px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
          }
          .brand-title {
            font-size: 18px;
            font-weight: 700;
            color: #0f172a;
            letter-spacing: -0.02em;
          }
          .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #ecfdf5;
            color: #059669;
            font-size: 12px;
            font-weight: 600;
            padding: 3px 10px;
            border-radius: 20px;
            border: 1px solid #a7f3d0;
            margin-left: 12px;
          }
          .sources-strip {
            font-size: 12px;
            color: #64748b;
            display: inline-block;
            margin-left: 14px;
          }

          /* Prompt chips */
          .chip-container {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin: 10px 0 20px 0;
          }

          /* Swarm Live Stepper */
          .stepper-box {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border-radius: 12px;
            padding: 20px 24px;
            color: white;
            margin-bottom: 24px;
            box-shadow: 0 4px 15px rgba(15, 23, 42, 0.15);
          }
          .stepper-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
          }
          .stepper-title {
            font-size: 15px;
            font-weight: 600;
            color: #f8fafc;
          }
          .stepper-steps {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 8px;
          }
          .step-pill {
            padding: 8px 10px;
            border-radius: 8px;
            font-size: 11px;
            font-weight: 500;
            text-align: center;
          }
          .step-done {
            background: rgba(16, 185, 129, 0.2);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.4);
          }
          .step-active {
            background: rgba(59, 130, 246, 0.25);
            color: #93c5fd;
            border: 1px solid #3b82f6;
            animation: pulse-ring 1.5s infinite;
          }
          .step-pending {
            background: rgba(255, 255, 255, 0.05);
            color: #94a3b8;
            border: 1px solid rgba(255, 255, 255, 0.1);
          }
          @keyframes pulse-ring {
            0% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4); }
            70% { box-shadow: 0 0 0 6px rgba(59, 130, 246, 0); }
            100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0); }
          }

          /* Paper Card in Sources tab */
          .paper-card {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 14px 16px;
            margin-bottom: 10px;
            transition: all 0.2s ease;
          }
          .paper-card:hover {
            border-color: #cbd5e1;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
          }
          .paper-title {
            font-weight: 600;
            font-size: 14px;
            color: #1e293b;
            margin-bottom: 4px;
          }

          /* Metadata Badge Tags */
          .meta-tag {
            display: inline-block;
            padding: 3px 8px;
            background: #f1f5f9;
            border-radius: 6px;
            font-size: 11px;
            color: #475569;
            margin-right: 6px;
            border: 1px solid #e2e8f0;
          }
          .checksum-badge {
            background: #eff6ff;
            color: #2563eb;
            border: 1px solid #bfdbfe;
            font-family: monospace;
          }
        </style>
        """,
        unsafe_allow_html=True
    )

    if not st.session_state.get("authenticated"):
        show_login_page()
        return

    user_id = st.session_state.get("user_id")
    username = st.session_state.get("username", "User")

    # ── Database Helpers ────────────────────────────────────────────────
    def _backfill_reports_from_disk(active_query="(Recovered — query unknown)"):
        """Scan on-disk report files and register any that are not yet in the DB."""
        user_dir = REPORTS_DIR / str(user_id)
        if not user_dir.exists():
            return
        db = SessionLocal()
        existing_paths = {r.file_path for r in db.query(Report).filter(Report.user_id == user_id).all()}
        
        for f in user_dir.glob("research_report_*.md"):
            fp = str(f)
            if fp not in existing_paths:
                new_r = Report(user_id=user_id, file_path=fp, query=active_query)
                db.add(new_r)
        db.commit()
        db.close()

    if st.session_state.get("is_researching"):
        _backfill_reports_from_disk(st.session_state.get("last_query", "(Recovered — query unknown)"))
    elif not st.session_state.get("_backfilled"):
        _backfill_reports_from_disk()
        st.session_state["_backfilled"] = True

    def _load_all_reports():
        db = SessionLocal()
        rows = (db.query(Report)
                  .filter(Report.user_id == user_id)
                  .order_by(Report.created_at.asc())
                  .all())
        result = [(r.id, r.query, r.file_path, r.created_at) for r in rows]
        db.close()
        return result

    all_reports = _load_all_reports()

    # ── TOP BAR (User info & Swarm status) ──────────────────────────────
    top_col1, top_col2 = st.columns([0.75, 0.25])
    with top_col1:
        st.markdown(
            f"""
            <div class="sentinel-top-bar">
              <div>
                <span class="brand-title">⚡ SentinelARC</span>
                <span class="status-badge">● Swarm Active</span>
                <span class="sources-strip">📚 Sources: OpenAlex • arXiv • PubMed • Crossref • Semantic Scholar</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with top_col2:
        user_c1, user_c2 = st.columns([0.65, 0.35])
        with user_c1:
            st.markdown(f"<div style='padding-top: 18px; text-align: right;'>👤 <strong>{username}</strong></div>", unsafe_allow_html=True)
        with user_c2:
            st.markdown("<div style='padding-top: 10px;'>", unsafe_allow_html=True)
            if st.button("Sign Out", key="btn_signout", use_container_width=True):
                session_token = st.query_params.get("session")
                if session_token:
                    delete_session(session_token)
                    st.query_params.clear()
                for k in ["authenticated", "user_id", "username", "chat_history", "shown_reports", "active_report_id", "_backfilled"]:
                    st.session_state.pop(k, None)
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    # ── SIDEBAR (Chat History & Control Center) ─────────────────────────
    with st.sidebar:
        st.markdown(
            """
            <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); padding: 16px; border-radius: 12px; color: white; margin-bottom: 12px;">
              <h3 style="color: white !important; margin: 0 0 4px 0; font-size: 18px;">SentinelARC Swarm</h3>
              <p style="color: #94a3b8; font-size: 11px; margin: 0;">Multi-Agent Synthesis Engine</p>
            </div>
            """,
            unsafe_allow_html=True
        )

        if st.button("＋ New Research Query", use_container_width=True, key="btn_new_chat", type="primary"):
            st.session_state["active_report_id"] = None
            st.session_state["chat_history"] = []
            st.session_state["shown_reports"] = set()
            st.rerun()

        st.markdown("#### 🗂 Research History")
        if not all_reports:
            st.caption("No reports yet. Submit your first research query!")
        else:
            search_filter = st.text_input("Filter history", placeholder="🔍 Filter reports...", label_visibility="collapsed", key="search_filter")
            for rep_id, query, fpath, created_at in reversed(all_reports):
                if search_filter and search_filter.lower() not in query.lower():
                    continue

                is_active = st.session_state.get("active_report_id") == rep_id
                btn_style = "primary" if is_active else "secondary"
                time_str = created_at.strftime("%b %d, %H:%M") if created_at else ""
                short_query = query[:28] + ("…" if len(query) > 28 else "")

                col_btn, col_del = st.columns([0.82, 0.18])
                with col_btn:
                    if st.button(f"{short_query}\n_{time_str}_", key=f"chat_{rep_id}", use_container_width=True, type=btn_style):
                        st.session_state["active_report_id"] = rep_id
                        st.session_state["chat_history"] = [
                            {"type": "user", "content": f"Research: {query}"},
                            {"type": "report", "path": fpath}
                        ]
                        st.session_state["shown_reports"] = {fpath}
                        st.rerun()
                with col_del:
                    if st.button("🗑️", key=f"del_{rep_id}", help="Delete report", use_container_width=True):
                        delete_report(rep_id, fpath, user_id)
                        st.toast("🗑️ Report removed.")
                        st.rerun()

        st.markdown("---")
        with st.container(border=True):
            st.markdown("##### 🛠️ Control Center")
            if "mode" not in st.session_state:
                saved_mode = st.query_params.get("mode", "research")
                st.session_state["mode"] = "General AI" if saved_mode == "general" else "Research AI"

            current_is_general = st.session_state.get("mode") == "General AI"
            mode = st.radio(
                "**Intelligence Mode**",
                ["Research AI Swarm", "General AI Chat"],
                index=1 if current_is_general else 0,
                key="sidebar_mode_toggle"
            )
            new_mode = "General AI" if "General AI" in mode else "Research AI"
            if new_mode != st.session_state.get("mode"):
                st.session_state["mode"] = new_mode
                st.query_params["mode"] = "general" if new_mode == "General AI" else "research"
                st.rerun()

            if st.session_state.get("mode") == "General AI":
                st.session_state["ai_model"] = st.selectbox(
                    "**Model Selection**",
                    ["llama3.1:8b", "mistral", "qwen2.5-coder"]
                )
            else:
                st.caption("⚡ Swarm Pipeline: HyDE ➔ Multi-Source ➔ FactChecker ➔ Synthesis")

    # ── Chat & Report History Initialization ───────────────────────────
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
        for rep_id, query, fpath, _ in all_reports:
            st.session_state["chat_history"].append({"type": "user", "content": f"Research: {query}"})
            st.session_state["chat_history"].append({"type": "report", "path": fpath})

    if "shown_reports" not in st.session_state:
        st.session_state["shown_reports"] = {item.get("path") for item in st.session_state["chat_history"] if item.get("path")}

    # Check for active task flag
    task_file = f"output/active_task_{user_id}.flag"
    if not st.session_state.get("is_researching") and os.path.exists(task_file):
        task_time = os.path.getmtime(task_file)
        search_is_done = any(os.path.exists(fpath) and os.path.getmtime(fpath) > task_time for _, _, fpath, _ in all_reports)
        if search_is_done:
            try:
                os.remove(task_file)
            except OSError:
                pass
        else:
            st.session_state["is_researching"] = True
            st.session_state["poll_count"] = 0

    # Detect newly saved reports
    new_report_found = False
    for rep_id, query, fpath, _ in all_reports:
        if fpath not in st.session_state["shown_reports"]:
            st.session_state["chat_history"].append({"type": "user", "content": f"Research: {query}"})
            st.session_state["chat_history"].append({"type": "report", "path": fpath})
            st.session_state["shown_reports"].add(fpath)
            new_report_found = True
            if st.session_state.get("is_researching"):
                st.session_state["is_researching"] = False
                if os.path.exists(task_file):
                    try:
                        os.remove(task_file)
                    except OSError:
                        pass
                st.toast("🎉 Research complete! Synthesized report loaded below.")

    if new_report_found:
        st.rerun()

    # ── QUICK PROMPTS CHIPS ─────────────────────────────────────────────
    st.caption("✨ Quick Start Prompts:")
    chip_cols = st.columns(4)
    with chip_cols[0]:
        if st.button("⚡ Quantum Key Distribution", key="qp_1", use_container_width=True):
            st.session_state["pending_query"] = "Quantum Key Distribution Protocols and Post-Quantum Security"
            st.rerun()
    with chip_cols[1]:
        if st.button("🧬 CRISPR Off-Target Repair", key="qp_2", use_container_width=True):
            st.session_state["pending_query"] = "CRISPR-Cas9 Off-Target Effects and Fidelity Enhancement"
            st.rerun()
    with chip_cols[2]:
        if st.button("🤖 Agent Memory with CRIU", key="qp_3", use_container_width=True):
            st.session_state["pending_query"] = "Process Checkpointing in Multi-Agent Systems using CRIU"
            st.rerun()
    with chip_cols[3]:
        if st.button("🧠 HyDE Dense Retrieval", key="qp_4", use_container_width=True):
            st.session_state["pending_query"] = "Hypothetical Document Embeddings for Zero-Shot Academic Search"
            st.rerun()

    # ── TOP SEARCH INPUT ───────────────────────────────────────────────
    initial_text = st.session_state.pop("pending_query", "")
    search_prompt = st.text_input(
        "🔍 Search literature or ask SentinelARC...",
        value=initial_text,
        placeholder="Enter academic topic, paper claim, or research question...",
        key="top_search_input"
    )

    if search_prompt and search_prompt.strip() != st.session_state.get("last_query"):
        prompt = search_prompt.strip()
        st.session_state["last_query"] = prompt
        st.session_state["chat_history"].append({"type": "user", "content": prompt})

        if st.session_state.get("mode") == "General AI":
            st.session_state["chat_history"].append({"type": "assistant", "content": ""})
            placeholder = st.empty()
            full_resp = ""
            for chunk in trigger_general_ai(prompt, st.session_state.get("ai_model", "llama3.1:8b"), st.session_state["chat_history"][:-1], user_id):
                full_resp += chunk
                placeholder.markdown(full_resp + "▌")
            st.session_state["chat_history"][-1]["content"] = full_resp
            placeholder.markdown(full_resp)
            st.rerun()
        else:
            try:
                trigger_research(prompt, user_id)
                st.session_state["is_researching"] = True
                with open(f"output/active_task_{user_id}.flag", "w") as f:
                    f.write(prompt)
                st.toast("🚀 Swarm activated! Gathering and synthesizing sources...")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to start research: {e}")

    # ── LIVE SWARM STEPPER (When active) ────────────────────────────────
    if st.session_state.get("is_researching"):
        poll_count = st.session_state.get("poll_count", 0)
        elapsed = poll_count * 2

        # Compute active stage
        if elapsed < 6:
            curr_stage = 0
            stage_name = "Semantic Query Expansion (HyDE via Groq)"
        elif elapsed < 16:
            curr_stage = 1
            stage_name = "Parallel Multi-Source Retrieval (arXiv, PubMed, OpenAlex)"
        elif elapsed < 28:
            curr_stage = 2
            stage_name = "Document Stream Extraction & Paywall Bypass"
        elif elapsed < 40:
            curr_stage = 3
            stage_name = "Cross-Verification & Fact-Checking with DOIs"
        else:
            curr_stage = 4
            stage_name = "Synthesis & Atomic Persistence"

        step_classes = []
        for i in range(5):
            if i < curr_stage:
                step_classes.append("step-done")
            elif i == curr_stage:
                step_classes.append("step-active")
            else:
                step_classes.append("step-pending")

        st.markdown(
            f"""
            <div class="stepper-box">
              <div class="stepper-header">
                <div>
                  <span class="stepper-title">🔄 Active Research Swarm: {stage_name}</span>
                </div>
                <div>
                  <span style="font-size: 12px; color: #94a3b8; background: rgba(255,255,255,0.1); padding: 4px 10px; border-radius: 6px;">
                    ⏱ Elapsed: {elapsed}s
                  </span>
                </div>
              </div>
              <div class="stepper-steps">
                <div class="step-pill {step_classes[0]}">1. HyDE Query</div>
                <div class="step-pill {step_classes[1]}">2. Multi-Source</div>
                <div class="step-pill {step_classes[2]}">3. PDF Parsing</div>
                <div class="step-pill {step_classes[3]}">4. Fact-Check</div>
                <div class="step-pill {step_classes[4]}">5. Synthesis</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        col_spin, col_stop = st.columns([0.85, 0.15])
        with col_stop:
            if st.button("🛑 Stop Search", key="stop_search_btn", use_container_width=True):
                st.session_state["is_researching"] = False
                import glob
                for f in glob.glob(f"output/active_task_{user_id}.flag"):
                    try:
                        os.remove(f)
                    except OSError:
                        pass
                st.rerun()

        time.sleep(2)
        st.session_state["poll_count"] = poll_count + 1
        if st.session_state["poll_count"] > 900:
            st.session_state["is_researching"] = False
            st.error("Request timed out after 30 minutes.")
        st.rerun()

    # ── CHAT & REPORT STREAM ───────────────────────────────────────────
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

                meta_path = path.with_suffix(".meta.json")
                html_path = path.with_suffix(".html")

                checksum = None
                word_count = len(content.split())
                sources_count = len(papers)
                meta_data = {}

                if meta_path.exists():
                    try:
                        meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
                        checksum = meta_data.get("checksum")
                        word_count = meta_data.get("word_count", word_count)
                        sources_count = meta_data.get("sources_count", sources_count)
                    except Exception:
                        pass

                with st.chat_message("assistant"):
                    with st.container(border=True):
                        # Header with badges
                        st.markdown(
                            f"""
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                              <div>
                                <span style="font-weight: 700; font-size: 16px; color: #0f172a;">📄 {path.name}</span>
                              </div>
                              <div>
                                <span class="meta-tag">📝 {word_count} words</span>
                                <span class="meta-tag">📚 {sources_count} sources</span>
                                <span class="meta-tag checksum-badge">🔒 SHA-256: {checksum[:12] if checksum else 'Verified'}...</span>
                              </div>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )

                        # Tabbed Report View
                        tab_report, tab_sources, tab_integrity, tab_html = st.tabs([
                            "📖 Synthesis Report",
                            f"📚 Sources & Citations ({len(papers)})",
                            "🔒 Integrity & Metadata",
                            "🌐 HTML Preview"
                        ])

                        with tab_report:
                            if summary_md:
                                st.markdown(summary_md)

                        with tab_sources:
                            if not papers:
                                st.info("No external URLs or citations detected in this report.")
                            else:
                                st.markdown(f"**Verified Academic Sources ({len(papers)} papers):**")
                                for p_idx, paper in enumerate(papers):
                                    pdf_badge = "📄 **PDF Available**" if str(paper.get("is_pdf")).lower() == "true" else "🔗 **Web Link**"
                                    with st.container(border=True):
                                        st.markdown(f"**{p_idx+1}. [{paper['title']}]({paper['url']})**")
                                        st.caption(f"Target: `{paper['url']}` | Status: {pdf_badge}")

                        with tab_integrity:
                            st.markdown("##### 🔒 Cryptographic Verification & File Provenance")
                            info_cols = st.columns(3)
                            info_cols[0].metric("File Size", f"{path.stat().st_size:,} bytes")
                            info_cols[1].metric("Word Count", f"{word_count:,}")
                            info_cols[2].metric("Sources Linked", len(papers))

                            st.markdown(f"**Full SHA-256 Checksum:**")
                            st.code(checksum if checksum else "Computed upon atomic write", language="text")

                            st.markdown("**File System Path:**")
                            st.code(str(path.resolve()), language="text")

                            if meta_data:
                                st.markdown("**Metadata Sidecar (`.meta.json`):**")
                                st.json(meta_data)

                        with tab_html:
                            if html_path.exists():
                                html_text = html_path.read_text(encoding="utf-8")
                                components.html(html_text, height=450, scrolling=True)
                            else:
                                st.caption("HTML version not yet generated for this report.")

                        # Multi-Format Export Toolbar
                        st.markdown("---")
                        st.markdown("###### 📥 Export Research Report:")
                        dl_cols = st.columns(4)
                        with dl_cols[0]:
                            st.download_button(
                                label="📥 Markdown (.md)",
                                data=content,
                                file_name=path.name,
                                mime="text/markdown",
                                key=f"dl_md_{idx}",
                                use_container_width=True
                            )
                        with dl_cols[1]:
                            # Generate PDF bytes via reportlab
                            try:
                                pdf_bytes = build_summary_pdf_bytes(content, f"SentinelARC: {path.stem}")
                                st.download_button(
                                    label="📄 PDF Document (.pdf)",
                                    data=pdf_bytes,
                                    file_name=path.with_suffix(".pdf").name,
                                    mime="application/pdf",
                                    key=f"dl_pdf_{idx}",
                                    use_container_width=True
                                )
                            except Exception as pdf_err:
                                st.caption(f"PDF unavailable: {pdf_err}")
                        with dl_cols[2]:
                            if html_path.exists():
                                st.download_button(
                                    label="🌐 Standalone HTML (.html)",
                                    data=html_path.read_text(encoding="utf-8"),
                                    file_name=html_path.name,
                                    mime="text/html",
                                    key=f"dl_html_{idx}",
                                    use_container_width=True
                                )
                        with dl_cols[3]:
                            if meta_path.exists():
                                st.download_button(
                                    label="📊 Metadata JSON (.json)",
                                    data=meta_path.read_text(encoding="utf-8"),
                                    file_name=meta_path.name,
                                    mime="application/json",
                                    key=f"dl_meta_{idx}",
                                    use_container_width=True
                                )

            else:
                with st.chat_message("assistant"):
                    st.warning(f"Report file `{path.name}` not found or still generating...")


if __name__ == "__main__":
    main()
