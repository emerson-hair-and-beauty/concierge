# Use public PyTorch base image (fixes torch compatibility issues)
FROM pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 1000 -r requirements.txt

# Copy the app code
COPY app/ ./app

# Expose port
EXPOSE 8000

# Run the app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
