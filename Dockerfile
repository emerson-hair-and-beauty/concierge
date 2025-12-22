# Use the existing image which already has heavy dependencies like PyTorch and transformers
FROM emersonapps/fastapi-app:latest

# Set working directory
WORKDIR /app

# The existing image already has the models and libs. 
# We only copy the latest code updates here.

# Copy the app code
COPY app/ ./app

# Expose the port FastAPI will run on
EXPOSE 8000

# Run FastAPI with Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]