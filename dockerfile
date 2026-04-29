FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    build-essential \
    libsndfile1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app
COPY VERSION /app/version.txt

EXPOSE 9006

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9006"]