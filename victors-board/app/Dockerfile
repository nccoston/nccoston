FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DATA_DIR=/data
VOLUME /data
EXPOSE 8080

# Single worker: the ephemeral chat lives in process memory, so all requests
# must share one process. Threads carry the concurrency instead.
CMD ["gunicorn", "-b", "0.0.0.0:8080", "--workers", "1", "--threads", "16", "app:app"]
