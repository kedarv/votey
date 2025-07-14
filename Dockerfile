FROM python:3.12-slim

# Set environment variables for Poetry
ENV POETRY_VERSION=2.1.3 \
    POETRY_HOME=/opt/poetry \
    POETRY_CACHE_DIR=/opt/.cache \
    PATH="/opt/poetry/bin:$PATH"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

# Set working directory
WORKDIR /app

# Copy dependency files first for better caching
COPY pyproject.toml poetry.lock ./

# Install dependencies
RUN poetry install --no-root --no-interaction --no-ansi

# Copy application code
COPY . .

# Expose the application port
EXPOSE 8000
ENV PORT=8000

# Run the application
CMD ["poetry", "run", "gunicorn", "run:app"]
