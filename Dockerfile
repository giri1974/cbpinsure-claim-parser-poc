# CBPInsure Claim Parser POC - container image for Render / Fly / any Docker host (Linux).
# Default DB is cloud Postgres (psycopg); RapidOCR (ONNX) for OCR. No ODBC/pyodbc on Linux.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DB_MODE=postgres \
    OCR_ENGINE=rapidocr \
    PORT=8080 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# System libs: libGL/glib for OpenCV used by RapidOCR; FreeTDS for pymssql; poppler for pdf rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 freetds-bin freetds-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for layer caching. pyodbc line is win32-only and is skipped on Linux.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8080

# Bind to the platform-provided $PORT (Render sets it); default 8080.
CMD ["sh", "-c", "streamlit run app.py --server.port=${PORT:-8080} --server.address=0.0.0.0 --server.headless=true --server.enableCORS=false --server.enableXsrfProtection=false"]
