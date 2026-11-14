# SentinelARC User Guide

> **User Manual & Dashboard Walkthrough**: Learn how to interact with SentinelARC through its responsive Streamlit web dashboard (`http://localhost:8501`), initiate deep research tasks, inspect grounded fact-checking matrices, and export academic survey papers.

---

## 1. Accessing the Dashboard

Once the SentinelARC services are started via Docker Compose or locally:
1. Open your web browser and navigate to:
   ```
   http://localhost:8501
   ```
2. You will be greeted by the **SentinelARC Security Gateway**.

---

## 2. Authentication & Data Isolation

To guarantee total data privacy and user separation, all reports and histories are strictly scoped to authenticated user accounts.

### Account Registration & Login
1. **New Users**: Select the **Register** tab. Enter a unique username and password.
   - *Security Note*: Passwords of any length are supported. SentinelARC applies SHA-256 pre-hashing before bcrypt encryption to guarantee maximum entropy.
2. **Existing Users**: Select the **Login** tab and enter your credentials.
3. Upon successful authentication, your user session is initialized, and your private research library is mounted.

---

## 3. The Dashboard Layout

The interface is structured into two main workspaces:

```
┌───────────────────────────────┬────────────────────────────────────────────────────────┐
│           SIDEBAR             │                       MAIN VIEW                        │
│                               │                                                        │
│ • User Profile & Logout       │ • Mode Switcher:                                       │
│ • System & Agent Health       │   [ Deep Research Swarm ]  [ Direct LLM Bypass ]       │
│ • LLM Engine Selector:        │                                                        │
│   (Groq Cloud / Local Ollama) │ • Chat / Prompt Input Box                              │
│ • Past Research Reports:      │ • Live Progress Indicator (Searching, Extracting...)  │
│   - Select previous report    │ • Report Viewer:                                       │
│   - Download Markdown (.md)   │   - Executive Consensus & Disagreement Banner          │
│   - Download Standalone HTML  │   - Comparative Technical Matrix Table                 │
│                               │   - Thematic Synthesis & Open Challenges               │
│                               │   - Grounded Epistemic Bibliography                    │
└───────────────────────────────┴────────────────────────────────────────────────────────┘
```

---

## 4. Operating Modes

SentinelARC provides two operational modes selectable via the top toggle or prompt context:

### Mode A: Deep Research Swarm (Primary Mode)
- **When to Use**: Academic literature surveys, technical benchmark comparisons, fact-checking controversial claims, and deep architectural analyses.
- **How It Works**:
  1. Enter your academic prompt (e.g., *"Direct Preference Optimization vs RLHF: Sample Efficiency and Overfitting Vulnerabilities"*).
  2. Click **Submit** or press **Enter**.
  3. The multi-agent swarm activates over RabbitMQ:
     - 🔍 **Search Agent**: Gathers papers across OpenAlex, Semantic Scholar, arXiv, PubMed, and Crossref; calculates Citation Velocity; builds 1-hop lineage trees.
     - 📄 **Extraction Agent**: Downloads full PDFs, strips reference sections to preserve tokens, and extracts empirical benchmarks.
     - 🛡️ **Fact-Checker Agent**: Runs the 4-Layer Grounded NLI Funnel, matching numerical metrics and detecting scientific consensus vs debate.
     - ✍️ **Synthesis Agent**: Generates the 5-Part Survey Paper with comparative matrix and inline citations.
     - 💾 **File Save Agent**: Atomically writes Markdown and HTML exports to `/output/reports/{user_id}/` and registers the report in SQLite.
  4. Average turnaround: **22–31 seconds**.

### Mode B: Direct Bypass (General Chat Mode)
- **When to Use**: Quick conceptual queries, code syntax questions, or conversational brainstorming where multi-agent web retrieval is unnecessary.
- **How It Works**:
  - The request bypasses the AMQP agent swarm and connects directly to the high-speed LLM engine via `POST /general_chat`.
  - Streamed response appears in sub-second latency (< 800ms).

---

## 5. Inspecting Research Reports

When a Deep Research cycle completes, the resulting report is displayed with rich interactive formatting:

### 1. Executive Consensus & Disagreement Banner
- Displays an immediate executive summary of findings.
- Highlights whether literature exhibits **Scientific Consensus** or **Contested Scientific Debate**.
- Displays the calibrated Epistemic Confidence percentage.

### 2. Comprehensive Comparative Technical Matrix
A structured table comparing the analyzed papers:
- **Paper / Model**: Title and seminal anchor tag.
- **Datasets / Benchmarks**: Testbeds evaluated (e.g., ImageNet, GSM8K, GLUE).
- **Reported Metrics**: Key empirical speedups, accuracies, or parameter counts.
- **NLI Entailment**: Verification status (`VERIFIED`, `CONTRADICTION`, `NEUTRAL`).
- **Epistemic Tier**: Authority ranking based on peer review and citation velocity.

### 3. Clickable Inline Citations & Bibliography
- Every scientific claim in the prose is anchored with a clickable inline citation link (e.g., `[Vaswani et al., 2017](https://doi.org/...)` or `[^1]`).
- The bibliography lists verified DOIs, author lists, and open-access PDF links.

---

## 6. Exporting Reports

Reports are permanently stored in your user directory:
- **Markdown (.md)**: Raw GitHub-Flavored Markdown report with tables and equations.
- **HTML Export**: Standalone HTML document with responsive typography and embedded stylesheets, ready for distribution or printing.
- **Metadata Sidecar (.meta.json)**: JSON file containing cryptographic SHA-256 hash, execution timestamps, source counts, and validation metrics.

To download, use the **Download Markdown** or **Download HTML** buttons in the sidebar under your active report.
