FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The package is served as `booking` so its relative imports (from .plato …) work.
COPY *.py /app/booking/

# ONE worker so the per-clinician threading.Lock in booking.py is authoritative
# (paired with Cloud Run --max-instances=1). Work is I/O-bound (Plato + BigQuery),
# so threads handle concurrency. 60s timeout: a booking is a couple of Plato
# round-trips, not a heavy build.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 60 booking.app:app
