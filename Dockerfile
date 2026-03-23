FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY growthclaw/ growthclaw/

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Create data directories
RUN mkdir -p /root/.growthclaw/memory /var/log/growthclaw

# Default environment
ENV GROWTHCLAW_DRY_RUN=true
ENV PYTHONUNBUFFERED=1

# Expose dashboard port
EXPOSE 8501

# Default: run the GrowthClaw daemon (CDC listener + scheduler)
CMD ["python", "-m", "growthclaw.cli", "start"]
