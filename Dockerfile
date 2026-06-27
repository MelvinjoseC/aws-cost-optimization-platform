# Multi-stage build to reduce final image size and enhance security
FROM python:3.10-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file to install dependencies
COPY requirements.txt .

# Install dependencies into a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# Final runtime image
FROM python:3.10-slim AS runner

WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source files
COPY src/ ./src/
COPY lambda/ ./lambda/

# Configure application environment defaults
ENV PYTHONUNBUFFERED=1

# Create a non-root system group and user for security hardening
RUN groupadd -g 10001 appgroup && \
    useradd -u 10000 -g appgroup -m -s /bin/bash appuser

# Set proper ownership for the application workspace
RUN chown -R appuser:appgroup /app

# Switch to the non-root user
USER 10000:10001

# Command to execute the scanning runner
CMD ["python", "lambda/handler.py"]
