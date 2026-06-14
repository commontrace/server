FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
# startCommand is supplied per-service by railway.*.toml
CMD ["python", "-m", "commontrace_ops.oss_audit"]
