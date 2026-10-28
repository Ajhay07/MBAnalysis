# Backend container for Railway deployment.
# Mirrors the documented safe install order in requirements.txt / README
# ("OCR vs. AI Vision Interpretation"): paddleocr must be installed with
# --no-deps, otherwise its own install_requires drags in a conflicting
# opencv-python build on top of opencv-python-headless.
#
# Same problem, one level deeper, with imgaug (installed below for paddleocr's own runtime
# use): imgaug has no --no-deps, and one of ITS transitive dependencies has no numpy upper
# bound either, so pip's resolver silently upgrades the numpy==1.26.4 pinned in
# requirements.txt to numpy 2.x - which breaks PaddleOCR outright, since imgaug/paddleocr's
# own code calls `np.sctypes`, an attribute NumPy 2.0 removed. This was traced directly to a
# real production failure: PaddleOCR never actually imported on Railway because of this,
# silently making every analysis come back with zero components. The explicit re-pin below
# forces numpy back down after imgaug's install, with --no-deps so it can't drag anything
# else along with it.

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
    && pip install --no-cache-dir pyclipper imgaug lmdb requests \
    && pip install --no-cache-dir --no-deps --force-reinstall numpy==1.26.4 \
    && python -c "from paddleocr import PaddleOCR" \
    && python -c "import numpy; assert numpy.__version__ == '1.26.4', numpy.__version__"

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
