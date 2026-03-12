# Case-IMS — Production Dockerfile for Render.com
FROM python:3.11-slim

# Install system dependencies for document/media processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-heb \
    poppler-utils \
    antiword \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directories (Render Disk mounts at /data)
RUN mkdir -p /data/uploads

# Expose port (Render uses 10000 by default for Docker)
EXPOSE 10000

# Start the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
