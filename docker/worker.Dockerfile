# docker/worker.Dockerfile — GPU worker for Shortz
#
# Uses NVIDIA CUDA base for GPU inference.
# Falls back to CPU if no GPU is present.
#
# Build:
#   docker build -f docker/worker.Dockerfile -t shortz-worker .
#
# Run with GPU access:
#   docker run --gpus all shortz-worker

FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# System deps: Python 3.11, ffmpeg, ffprobe
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3-pip \
        ffmpeg \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Make python3.11 the default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY core/ core/
COPY redis_queue.py .
COPY worker.py .
COPY Shortz.py .
COPY voices/ voices/
COPY input/ input/

# GPU selection via environment variable (default: GPU 0)
ENV GPU_ID=0
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility

# Worker starts and blocks on the Redis queue
CMD ["python", "worker.py"]
