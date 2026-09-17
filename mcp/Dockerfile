# Reproducible build: dependencies come from requirements.txt with pinned versions and
# hashes (regenerate with scripts/lock-deps.sh), the package itself is installed without
# resolving anything. Runs as a fixed non-root uid that matches docker-compose.yml.
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1
# Apply Debian security updates so the image does not ship known-fixed OS CVEs. CI scans the
# built image with Trivy and fails on any fixable HIGH or CRITICAL finding.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

FROM base AS build
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps .

FROM base
RUN useradd --uid 10001 --user-group --no-create-home mcp \
    && mkdir -p /state && chown mcp:mcp /state
COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin/compliance-* /usr/local/bin/
USER mcp
EXPOSE 8765
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=2).status == 200 else 1)"
CMD ["compliance-mcp"]
