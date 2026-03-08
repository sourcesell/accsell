FROM python:3.11-slim

# System deps for Pillow fonts
RUN apt-get update && apt-get install -y \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot
COPY code.py .

# Uploads folder
RUN mkdir -p uploads

CMD ["python", "-u", "code.py"]
