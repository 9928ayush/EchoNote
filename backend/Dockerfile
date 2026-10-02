FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock \
    && pip install --no-cache-dir supervisor==4.3.0

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY supervisord.conf ./
COPY start_render.sh ./

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]