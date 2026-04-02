FROM python:3.11-slim

WORKDIR /app

# Copy backend files
COPY backend/ .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 8000

# Run with gunicorn for production
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
