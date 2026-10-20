FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    CAUSALGATE_API_AUDIT_LOG=/data/decisions.jsonl

WORKDIR /app

COPY requirements.txt requirements-server.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt -r requirements-server.txt

COPY . .

RUN useradd --create-home --uid 10001 causalgate \
    && mkdir -p /data \
    && chown causalgate:causalgate /data

USER causalgate

EXPOSE 7860

CMD ["python", "-m", "uvicorn", "causalgate.api.server:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1", "--no-proxy-headers"]
