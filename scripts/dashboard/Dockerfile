FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py template.html ./

# Cloud Run sends a SIGTERM and waits up to the grace period before SIGKILL.
# 2 workers x 4 threads handles the trickle of traffic for this dashboard.
CMD exec gunicorn --bind :$PORT --workers 2 --threads 4 --timeout 60 app:app
