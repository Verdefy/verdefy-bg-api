FROM python:3.11-slim

WORKDIR /app

# Install system deps for image processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the AI model so container starts instantly
RUN python -c "from rembg import new_session; new_session('u2netp')"

COPY app.py .

EXPOSE 8080
CMD gunicorn app:app --bind 0.0.0.0:${PORT:-8080} --timeout 120 --workers 1
