FROM python:3.11-slim
WORKDIR /app

# Upgrade pip and setuptools first (setuptools.backends requires >=68)
RUN pip install --no-cache-dir --upgrade pip setuptools

# NOTE: torch, sentence-transformers, and the embedder package are
# deliberately NOT installed here. mcp_server delegates embedding to
# ingestion via POST /embed. Do not reintroduce these dependencies without
# revisiting tools._fetch_embedding and the single-source-of-truth contract.

# Install mcp_server dependencies
COPY mcp_server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mcp_server/mcp_server/ mcp_server/

RUN useradd -m -u 1001 appuser
USER appuser

CMD ["python", "-m", "mcp_server.main"]
