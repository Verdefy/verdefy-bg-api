FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the selected high-detail model while building. This prevents the
# first customer upload from waiting for a large model download.
ARG BG_MODEL=birefnet-general
ENV BG_MODEL=${BG_MODEL}
RUN python -c "import os; from rembg import new_session; new_session(os.environ['BG_MODEL']); print('Model ready:', os.environ['BG_MODEL'])"

COPY app.py .

EXPOSE 8080
CMD gunicorn app:app --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 2 --timeout 180
