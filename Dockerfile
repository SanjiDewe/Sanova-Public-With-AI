FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml .
COPY app ./app

RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 sanova \
    && mkdir -p /tmp/sanova/tasks /tmp/sanova/audit \
    && chown -R sanova:sanova /tmp/sanova

USER sanova

CMD ["sh", "-c", "uvicorn app.web.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
