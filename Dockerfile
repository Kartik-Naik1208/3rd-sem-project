# ==============================================================================
# IngredientIQ - Production Dockerfile for Render & Linux Deployments
# Installs Tesseract OCR (with English, Hindi, and OSD language packs),
# OpenCV runtime dependencies, and starts Gunicorn on Render's dynamic PORT.
# ==============================================================================

FROM python:3.12-slim-bookworm

# Environment settings for optimal Python execution in containers
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PORT=10000 \
    FLASK_ENV=production

# Set working directory
WORKDIR /app

# 1. Install Linux system packages:
#    - tesseract-ocr, tesseract-ocr-eng, tesseract-ocr-osd, tesseract-ocr-hin
#    - libgl1, libglib2.0-0 for OpenCV headless/GUI image manipulation
#    - ca-certificates for secure outbound SMTP and database TLS connections
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-osd \
    tesseract-ocr-hin \
    libgl1 \
    libglib2.0-0 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 2. Verify Tesseract binary and language models during Docker image build
RUN which tesseract && tesseract --version && tesseract --list-langs

# 3. Install Python dependencies from requirements.txt with layer caching
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 4. Copy the application source code into the image
COPY . /app

# 5. Ensure runtime folders for instance database and uploads exist
RUN mkdir -p /app/instance /app/app/static/uploads

# 6. Verify end-to-end OCR and Flask application readiness at build time
RUN python verify_ocr.py

# Expose Render standard container port
EXPOSE 10000

# 7. Start application via Gunicorn bound to 0.0.0.0 and Render's dynamic $PORT
CMD ["sh", "-c", "gunicorn run:app --bind 0.0.0.0:${PORT:-10000} --workers 2 --threads 4 --timeout 120"]
