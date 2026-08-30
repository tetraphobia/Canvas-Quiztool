FROM python:3.12-slim

WORKDIR /app

# Copy dependency spec and source together so pip resolves everything at once
COPY pyproject.toml ./
COPY canvas_code_bot/ ./canvas_code_bot/
RUN pip install --no-cache-dir .

# Persistent data directory (SQLite + APScheduler jobstore live here)
RUN mkdir -p /data \
    && useradd -m -u 1000 botuser \
    && chown botuser /data
USER botuser

# Defaults — override via .env / environment: in compose
ENV APP_MODE=development
ENV DB_URL=sqlite:////data/quizbot.db

CMD ["python", "-m", "canvas_code_bot"]
