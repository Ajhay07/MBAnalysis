# Backend container for Railway deployment.
# Mirrors the documented safe install order in requirements.txt / README
# ("OCR vs. AI Vision Interpretation"): paddleocr must be installed with
# --no-deps, otherwise its own install_requires drags in a conflicting
# opencv-python build on top of opencv-python-headless.
#
# Same problem, one level deeper, with imgaug (installed below for paddleocr's own runtime
# use): imgaug has no --no-deps, and its own transitive deps (opencv-python, scikit-image)
# have no numpy upper bound, so pip's resolver upgrades numpy past the 1.26.4 pinned in
# requirements.txt to 2.x - and imgaug's own code calls `np.sctypes`, an attribute NumPy 2.0
# removed outright, so PaddleOCR never actually imported on Railway, silently making every
# analysis come back with zero components.
#
# We previously tried forcing numpy back down to 1.26.4 with a `--force-reinstall` step right
# after imgaug's install. That is WORSE: by the time that step runs, several heavy C-extension
# packages (opencv-python, scikit-image, scipy) are already unpacked against numpy 2.x, and
# ripping numpy's files out from under them mid-build crashed the Docker build itself with a
# native "free(): invalid pointer" error and a PaddlePaddle SIGABRT (exit code 134) - no image
# could even be produced. So we no longer fight pip's resolver here: numpy is left to resolve
# to whatever pip naturally picks (2.x), and the one attribute imgaug needs is polyfilled in
# Python instead - see the np.sctypes shim at the top of app/services/paddle_ocr.py, which
# runs before paddleocr (and therefore imgaug) is ever imported.

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
    && python -c "\
import numpy as np; \
np.sctypes = np.sctypes if hasattr(np, 'sctypes') else {'int': [np.int8, np.int16, np.int32, np.int64], 'uint': [np.uint8, np.uint16, np.uint32, np.uint64], 'float': [np.float16, np.float32, np.float64], 'complex': [np.complex64, np.complex128], 'others': [bool, object, bytes, str, np.void]}; \
from paddleocr import PaddleOCR"

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
