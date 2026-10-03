# Orbit on a Hugging Face Space (Docker). This folder is copied into the Space
# repo by .github/workflows/deploy-space.yml on every push to main, together with
# ORBIT_REPO and ORBIT_COMMIT, so the Space always builds the code GitHub has.

# 1. The web terminal (static files the API serves).
FROM node:22-slim AS web
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
COPY ORBIT_REPO ORBIT_COMMIT /tmp/
RUN git clone --quiet "https://github.com/$(cat /tmp/ORBIT_REPO).git" /src \
 && git -C /src checkout --quiet "$(cat /tmp/ORBIT_COMMIT)"
WORKDIR /src/web
RUN npm ci --no-audit --no-fund && npm run build && rm -rf node_modules

# 2. The API, with the code checkout (its .git is where the data sync keeps its worktree).
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Spaces run as uid 1000.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_SYNC=1
WORKDIR /home/user/app
COPY --chown=user --from=web /src /home/user/app
RUN uv sync --frozen --no-dev

ENV ORBIT_CLOUD=1 \
    ORBIT_API_HOST=0.0.0.0 \
    ORBIT_API_PORT=7860 \
    ORBIT_DATA_SYNC_REMOTE=data \
    ORBIT_DATA_SYNC_JOURNAL=1 \
    ORBIT_HOST_NAME=hf-space
EXPOSE 7860
CMD ["uv", "run", "--frozen", "--no-dev", "python", "-m", "orbit.cloud"]
