FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Served as the `careers` package so its relative imports work. Tests are left
# out by .gcloudignore; the operator CLI (admin.py) ships but nothing runs it here.
COPY *.py /app/careers/

# ONE worker so the in-process locks in pipeline.py (per-submission and the
# reference counter) are authoritative, paired with --max-instances=1. Work is
# I/O-bound (Drive/Sheets/SMTP), so threads cover concurrency. 120s timeout: a
# 10 MB upload on a slow phone link plus a few Google round-trips.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 120 careers.app:app
