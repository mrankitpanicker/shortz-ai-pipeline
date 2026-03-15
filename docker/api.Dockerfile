# docker/api.Dockerfile — FastAPI server for Shortz
FROM python:3.11-slim

WORKDIR /app

# Install only API dependencies (no GPU / TTS packages)
COPY requirements.txt .
RUN pip install --no-cache-dir \
    fastapi uvicorn redis pydantic

COPY core/ core/
COPY api_server.py .
COPY redis_queue.py .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "api_server:app", \
     "--host", "0.0.0.0", "--port", "8000"]
