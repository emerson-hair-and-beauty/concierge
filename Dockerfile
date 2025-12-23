# Use your existing image which already has all dependencies
FROM emersonapps/fastapi-app:latest

# Set working directory
WORKDIR /app

# Copy the updated app code
COPY app/ ./app

# Expose port
EXPOSE 8000

# Run the app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
