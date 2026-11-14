# Contributing to SentinelARC

Welcome to SentinelARC! This guide will help you set up your local development environment and understand the contribution process.

## Local Environment Setup

1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd SentinelARC
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   *(Note: For running tests, you may also need to install `pytest` if not globally installed.)*

4. **Environment Variables:**
   Copy the existing `.env` file or create one according to the specifications in `ENVIRONMENT_VARIABLES.md`.

## Running the Application

- **Core API (FastAPI):**
  ```bash
  python async_main.py
  ```
- **Web UI (Streamlit):**
  ```bash
  streamlit run streamlit_app.py
  ```

## Running Tests

To validate your changes, you can run the provided test scripts:

- **System Simple Test:**
  ```bash
  python test_system_simple.py
  ```
- **Workflow Test:**
  ```bash
  python workflow_test.py
  ```

## Coding Standards

- **Python Styling:** Follow PEP 8 guidelines.
- **Typing:** Use Python type hints (`typing` module) for function arguments and return types.
- **Asynchronous Code:** Ensure `async`/`await` is used properly, especially when interacting with RabbitMQ and external APIs.
- **Logging:** Use the built-in `logging` module (`logger.info`, `logger.error`) instead of raw `print` statements.
