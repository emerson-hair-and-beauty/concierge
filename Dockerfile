# Use PyTorch base image with CUDA support (PyTorch already installed!)
FROM pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime

# Set working directory inside container
WORKDIR /app

# Copy requirements first (for caching)
COPY requirements.txt .

# Install remaining dependencies (PyTorch already included in base image)
RUN pip install --no-cache-dir --timeout 1000 -r requirements.txt

# Copy the app code
COPY app/ ./app

# Expose the port FastAPI will run on
EXPOSE 8000

# Run FastAPI with Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]