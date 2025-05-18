# Stage 1: Builder
FROM python:3.9-slim-buster AS builder

WORKDIR /opt/venv

# Create a virtual environment
RUN python -m venv .
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runner
FROM python:3.9-slim-buster AS runner

WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY ./app /app/app
# COPY static /app/static # Line removed, will mount via docker-compose.yml

# Set path to include virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
