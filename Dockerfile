# CBPInsure Claim Parser POC - container image for Fly.io (Linux).
# Uses the cloud SQL Server (pymssql/FreeTDS) and RapidOCR (ONNX). No ODBC/pyodbc on Linux.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DB_MODE=cloud \
    OCR_ENGINE=rapidocr \
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

# Fly health checks hit the app port; bind to 0.0.0.0:8080
CMD ["streamlit", "run", "app.py", \
     "--server.port=8080", "--server.address=0.0.0.0", \
     "--server.headless=true", "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false"]
