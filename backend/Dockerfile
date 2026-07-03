FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim

WORKDIR /app
ENV PYTHONPATH=/app/src

# pg_dumpall for POST /permits/backup. Pulled from PGDG so the client major matches
# the Postgres 18 server (pg_dumpall refuses a newer server than itself).
RUN apt-get update
RUN apt-get install -y --no-install-recommends curl ca-certificates gnupg
RUN install -d /etc/apt/keyrings
RUN curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /etc/apt/keyrings/pgdg.asc
RUN echo "deb [signed-by=/etc/apt/keyrings/pgdg.asc] https://apt.postgresql.org/pub/repos/apt trixie-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list
RUN apt-get update
RUN apt-get install -y --no-install-recommends postgresql-client-18
RUN rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --no-install-project

COPY backend/alembic.ini backend/README.md ./
COPY backend/alembic ./alembic
COPY backend/src ./src
RUN uv sync

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

# Run migrations then serve. (Compose/k8s override the command as needed.)
CMD ["sh", "-c", "alembic upgrade head && uvicorn permits.main:app --host 0.0.0.0 --port 8000"]
