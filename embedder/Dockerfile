FROM python:3.11-slim
WORKDIR /app

# Install torch CPU-only first (much smaller on ARM64)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir sentence-transformers

COPY . .
RUN pip install --no-cache-dir -e .

# Pre-download the model during build so startup is instant
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

RUN useradd -m -u 1001 appuser
USER appuser
