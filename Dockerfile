# Alpaca MCP Server v2 — pinned, reproducible container image.
# Installs from PyPI rather than cloning the repo so the version is explicit.

FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Bump this to upgrade. Check https://pypi.org/project/alpaca-mcp-server/ for releases.
ARG ALPACA_MCP_VERSION=2.3.0

ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

RUN uv venv "$VIRTUAL_ENV" \
 && uv pip install --no-cache "alpaca-mcp-server==${ALPACA_MCP_VERSION}"

# Run unprivileged. This server holds brokerage credentials in its environment.
RUN useradd --create-home --uid 10001 alpaca
USER alpaca
WORKDIR /home/alpaca

EXPOSE 8000

# TCP liveness only — the MCP endpoint requires a proper POST handshake,
# so a socket check is the honest signal that the server is listening.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import socket,sys; s=socket.create_connection(('127.0.0.1',8000),3); s.close()" || exit 1

# 0.0.0.0 is required to be reachable from outside the container namespace.
# Host-side exposure is constrained by the port mapping in docker-compose.yml.
CMD ["alpaca-mcp-server", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]
