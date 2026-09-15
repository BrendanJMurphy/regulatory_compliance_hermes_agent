FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN useradd -u 10001 -m mcp
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && mkdir -p /state && chown mcp:mcp /state
USER mcp
EXPOSE 8765
CMD ["compliance-mcp"]
