FROM python:3.11-slim

WORKDIR /app

# minimal system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

# python deps
COPY requirements.txt .
RUN pip install --no-cache-dir fastapi uvicorn soundfile numpy onnxruntime onnx-asr python-multipart huggingface_hub

COPY src/server.py src/
COPY src/__init__.py src/

EXPOSE 8765
ENV NEMO_PORT=8765

CMD ["python", "src/server.py"]
