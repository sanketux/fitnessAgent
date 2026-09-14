FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FITNESS_AGENT_DB=/data/fitness.db \
    FITNESS_AGENT_CONTEXT=/app/context/sanket_health_agent_context.md

WORKDIR /app
COPY pyproject.toml README.md ./
COPY fitness_agent ./fitness_agent
COPY context ./context
RUN pip install --no-cache-dir ".[telegram]"

RUN useradd --create-home coach && mkdir -p /data && chown coach:coach /data
USER coach
VOLUME ["/data"]

CMD ["fitness-agent-telegram"]
