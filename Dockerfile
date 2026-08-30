FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN pip install --no-cache-dir uv

WORKDIR /app

# Install dependencies first so this layer is cached as long as
# pyproject.toml / uv.lock don't change (source changes shouldn't
# trigger a full dependency reinstall). Mirrors studylife-webhooks' Dockerfile.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# hatch-vcs derives the package version from git tags, but this image never COPYs .git
# (deliberately, to keep the dependency layer above cacheable across releases) - so
# building the project itself below has no VCS history to read. CI passes the exact
# semantic-release version it already computed as a build-arg (see the docker job in
# ci.yml). Un-suffixed SETUPTOOLS_SCM_PRETEND_VERSION, not the dist-specific
# _FOR_STUDYLIFE_ALEXA variant - hatch-vcs's own get_version() call never sets
# dist_name, so the dist-specific form is silently never read (same finding as
# studylife-mcp's Dockerfile).
ARG PACKAGE_VERSION=0.0.0+unknown
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${PACKAGE_VERSION}

COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

# /app/data must exist (and be owned by appuser) before the named volume mounts over it -
# otherwise Docker/Kubernetes auto-creates the mount point as root, and the non-root
# appuser below can't open its OAuth SQLite store there. /app itself also needs to be
# appuser-owned: the default ALEXA_OAUTH_DB_PATH ("oauth.db", relative) resolves under
# /app for anyone running this image without a data volume at all.
RUN mkdir -p /app/data && useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "studylife_alexa.main:app", "--host", "0.0.0.0", "--port", "8000"]
