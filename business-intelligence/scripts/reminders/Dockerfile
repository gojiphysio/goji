FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py reminder_mailer.py .
# Cloud Run Jobs invoke the container's entrypoint; no HTTP server needed.
ENTRYPOINT ["python", "-u", "main.py"]
