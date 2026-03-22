FROM python:3.11-slim

# System deps: FFmpeg + build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp binary (always latest)
RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
    -o /usr/local/bin/yt-dlp && chmod a+rx /usr/local/bin/yt-dlp

WORKDIR /app

# Install Python dependencies (cache layer)
COPY cloud/requirements.txt /app/cloud/requirements.txt
RUN pip install --no-cache-dir -r /app/cloud/requirements.txt \
    && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir openai-whisper \
    || echo "Whisper install failed — subtitles disabled"

# Copy source
COPY . /app

# Create runtime directories
RUN mkdir -p /app/cloud/logs /app/cloud/queue /app/cloud/downloads /app/cloud/output

WORKDIR /app/cloud

EXPOSE 8888

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["python", "main.py", "--daemon", "--no-ui"]
