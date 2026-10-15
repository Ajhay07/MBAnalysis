# Backend container for Railway deployment.
# Mirrors the documented safe install order in requirements.txt / README
# ("OCR vs. AI Vision Interpretation"): paddleocr must be installed with
# --no-deps, otherwise its own install_requires drags in a conflicting
# opencv-python build on top of opencv-python-headless.

FROM python:3.10-slim

# System libraries required by opencv-python-headless / PaddleOCR / PyMuPDF at import time.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

# Install everything except paddleocr first (pip ignores the paddleocr line only if we
# strip it out), then install paddleocr with --no-deps, then its real runtime deps,
# exactly as documented in requirements.txt / README.
RUN grep -v '^paddleocr==' requirements.txt > /tmp/requirements.base.txt \
    && pip install --no-cache-dir -r /tmp/requirements.base.txt \
    && pip install --no-cache-dir --no-deps paddleocr==2.7.3 \
    && pip install --no-cache-dir pyclipper imgaug lmdb requests

COPY . .

# Writable cache/data dirs. PaddleOCR downloads model weights to $HOME/.paddleocr (it has no
# dedicated cache-dir env var), so in production HOME, DATABASE_URL and UPLOAD_DIR are all
# pointed at the mounted Railway volume via env vars set on the Railway service (see
# DEPLOYMENT.md) - these defaults just ensure the container has somewhere writable without one.
ENV HOME=/app
RUN mkdir -p /app/.paddleocr /app/uploads

RUN chmod +x docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
