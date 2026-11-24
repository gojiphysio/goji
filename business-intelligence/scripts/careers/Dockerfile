FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Served as the `careers` package so its relative imports work. Tests are not
# shipped in the image.
COPY *.py /app/careers/
RUN rm -f /app/careers/test_*.py /app/careers/conftest.py /app/careers/dev_server.py

# ONE worker: reference numbers are allocated under an in-process lock (paired
# with Cloud Run --max-instances=1). Uploads are I/O-bound, so threads cover
# concurrency. 120s timeout: a 10MB CV upload to Drive on a slow day.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 120 careers.app:app
