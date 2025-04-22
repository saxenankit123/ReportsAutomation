FROM python:3

# Set the working directory
WORKDIR /app

# Copy project files
COPY . /app

# Install system dependencies for wkhtmltopdf
RUN apt-get update && apt-get install -y \
    wkhtmltopdf \
    fonts-noto  \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port Flask runs on
EXPOSE 5000

# Command to run the Flask app
CMD ["python", "app.py"]