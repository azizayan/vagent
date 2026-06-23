# syntax=docker/dockerfile:1.7
# Single-stage build. Pure-Python deps (no native compilation) make multi-stage
# unnecessary and harder to debug; one `pip install .` keeps versions pinned in
# one place (pyproject.toml) and produces a small enough image.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /srv

# Install dependencies from a minimal package first so ordinary source edits
# retain the expensive Pipecat/ONNX layer. The final source copy is imported
# directly from /srv/app at runtime.
COPY pyproject.toml ./
COPY app/__init__.py ./app/__init__.py

RUN pip install --upgrade pip && pip install .

COPY app ./app

USER app

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys;\
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2).status==200 else 1)" \
    || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
