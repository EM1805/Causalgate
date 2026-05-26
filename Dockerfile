FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860

WORKDIR /app

COPY requirements.txt requirements-server.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt -r requirements-server.txt

COPY . .

EXPOSE 7860

CMD ["uvicorn", "causalgate.api.server:app", "--host", "0.0.0.0", "--port", "7860"]
