# MCP do PostgreSQL (somente leitura). Build com contexto na raiz do BI_COMETA:
#   docker-compose -f docker/docker-compose.mcp.yml --env-file .env up -d --build
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY mcp_server/requirements.txt /app/mcp_server/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/mcp_server/requirements.txt

# O servidor lê o dicionário em ../docs relativo a ele (/app/docs).
COPY mcp_server/server.py /app/mcp_server/server.py
COPY docs/DATA_DICTIONARY.md /app/docs/DATA_DICTIONARY.md

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

ENV MCP_TRANSPORT=http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8001

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/healthz', timeout=3)"

CMD ["python", "mcp_server/server.py"]
