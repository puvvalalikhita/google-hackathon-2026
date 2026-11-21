FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static
COPY .env.example ./.env.example

RUN mkdir -p /app/data

ENV PORT=8080
ENV PYTHONUNBUFFERED=1
EXPOSE 8080

# Single worker preserves in-memory WebSocket session registry + SQLite WAL consistency on Cloud Run
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
