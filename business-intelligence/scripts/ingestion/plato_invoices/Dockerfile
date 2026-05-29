FROM python:3.12-slim

WORKDIR /app

# System deps kept minimal; google-cloud-bigquery is pure-python at install time.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Cloud Run Jobs invoke the container's entrypoint; no HTTP server needed.
ENTRYPOINT ["python", "-u", "main.py"]
