FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY app/ app/
COPY migrations/ migrations/
COPY alembic.ini .
COPY fixtures/ fixtures/
COPY scripts/ scripts/

# Install CPU-only PyTorch first (200MB vs 5GB with CUDA) — Railway has no GPU
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
