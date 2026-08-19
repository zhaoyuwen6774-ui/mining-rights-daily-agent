FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home app

COPY requirements.lock ./
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --requirement requirements.lock

COPY pyproject.toml README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --no-deps .

COPY data ./data
COPY tests ./tests
RUN mkdir -p /app/data/cache /app/output \
    && chown -R app:app /app

USER app

CMD ["mining-daily-agent", "给我生成一份关于 Pilbara 锂矿的今日简报", "--mode", "fixture"]
