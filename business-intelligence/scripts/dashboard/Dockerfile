FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py template.html ./
COPY static/ ./static/

# Cloud Run sends a SIGTERM and waits up to the grace period before SIGKILL.
# Single worker + many threads: the dashboard's in-process payload cache lives
# inside one Python process. With 2 workers, half the warm hits landed on a
# worker with an empty cache and rebuilt from scratch (observed: 46s warm
# latency). One worker keeps the cache shared across all requests. All work
# is I/O bound (BigQuery + HTTP), so threads beat extra processes here.
#
# Timeout aligned with Cloud Run's 300s request timeout: a cold /api/data
# build runs ~25 BQ queries, routinely 10-30s. Plato is no longer called on
# the hot path (appointments now come from BQ via plato-appointments-ingest).
CMD exec gunicorn --bind :$PORT --workers 1 --threads 16 --timeout 300 app:app
