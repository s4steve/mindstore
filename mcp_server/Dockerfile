FROM python:3.11-slim
WORKDIR /app

# Install torch CPU-only (ARM64 compatible)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir sentence-transformers

# Install embedder as a local package
COPY embedder/ /embedder/
RUN pip install --no-cache-dir /embedder

# Pre-download the model during build so startup is instant
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Install mcp_server dependencies
COPY mcp_server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mcp_server/mcp_server/ mcp_server/

RUN useradd -m -u 1001 appuser
USER appuser

CMD ["python", "-m", "mcp_server.main"]
