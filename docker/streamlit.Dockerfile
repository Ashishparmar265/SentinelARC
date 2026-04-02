FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Minimal dependencies for the Streamlit dashboard only.
# (Keeping this small avoids downloading the whole agent swarm stack.)
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        "streamlit>=1.40.0" \
        "reportlab>=4.0.0" \
        requests

# Copy the dashboard app + theme config
COPY streamlit_app.py .
COPY .streamlit/ .streamlit/

EXPOSE 8501

# The dashboard talks to the agent API by URL
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_PORT=8501

CMD ["streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]

