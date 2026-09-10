FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Trailing slash is required: a multi-source COPY needs a directory
# destination. Without it Docker fails with "the destination must be a
# directory and end with a /" — the sibling jobs copy a single file, so their
# `COPY main.py .` is fine and this doesn't carry over.
COPY main.py reminder_mailer.py ./
# Cloud Run Jobs invoke the container's entrypoint; no HTTP server needed.
ENTRYPOINT ["python", "-u", "main.py"]
