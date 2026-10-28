#!/usr/bin/env bash
# Exit on any error
set -e

echo "=== Starting Render Build ==="

# 1. Update package lists and install system binaries: Tesseract OCR, English data, and OpenCV runtime libraries
echo "Installing Tesseract OCR, English language data, and system libraries..."
apt-get update
apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0

echo "Verifying Tesseract binary installation..."
which tesseract || true
tesseract --version || true
tesseract --list-langs || true

# 2. Upgrade pip and install Python packages
echo "Installing Python dependencies from requirements.txt..."
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "=== Render Build Completed Successfully ==="
