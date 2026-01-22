#!/usr/bin/env python3
"""
nemo-smol server - a tiny asr server using parakeet 0.6b
"""
import os
import sys
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from pydantic import BaseModel
import uvicorn

MODEL = os.environ.get("NEMO_MODEL", "nemo-parakeet-tdt-0.6b-v3")
PORT = int(os.environ.get("NEMO_PORT", "8765"))

app = FastAPI(title="nemo-smol", version="0.1.0")
recognizer = None


class TranscribeResponse(BaseModel):
    text: str
    duration: float = 0.0


def load_model():
    global recognizer
    print("\n nemo-smol server")
    print(f" model: {MODEL}\n")

    try:
        import onnx_asr
        recognizer = onnx_asr.Recognizer(model=MODEL, quantization="int8")
        print(" ready!\n")
    except ImportError:
        print(" pip install onnx-asr")
        sys.exit(1)
    except Exception as e:
        print(f" {e}")
        sys.exit(1)


@app.on_event("startup")
async def startup():
    load_model()


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL}


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(file: UploadFile = File(...)):
    if not recognizer:
        raise HTTPException(503, "not ready")

    data = await file.read()
    if not data:
        raise HTTPException(400, "empty")

    suffix = Path(file.filename or "a.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(data)
        path = f.name

    try:
        t0 = time.time()
        text = recognizer.recognize(path)
        text = text if isinstance(text, str) else str(text)
        dur = time.time() - t0
        print(f" {dur:.1f}s | {text[:60]}")
        return TranscribeResponse(text=text.strip(), duration=dur)
    finally:
        try:
            os.unlink(path)
        except:
            pass


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
