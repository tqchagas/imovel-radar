FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The scheduler container runs off the same image with its own entrypoint.
RUN chmod +x /app/entrypoint.sh /app/scheduler.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
