# =========================================================
# Shortz — Production Dockerfile
# =========================================================
# Supports both API server and Worker via CMD override.
#
# Build:
#   docker build -t shortz .
#
# Run API:
#   docker run -p 8000:8000 shortz
#
# Run Worker:
#   docker run --gpus all shortz python worker.py
# =========================================================

FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    redis-tools \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code — core pipeline
COPY Shortz.py redis_queue.py worker.py api_server.py ./

# Services layer
COPY services/ ./services/

# Monitoring layer
COPY monitoring/ ./monitoring/

# Assets
COPY input/ ./input/
COPY voices/ ./voices/
COPY bin/ ./bin/

# Output + logs directories
RUN mkdir -p output/hindi output/subtitles output/video logs

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

EXPOSE 8000 8070

# Default: run the API server
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"]