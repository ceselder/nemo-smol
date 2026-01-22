#!/usr/bin/env python3
"""
nemo-smol sounds - cute audio feedback

generates simple sine wave blips if sound files don't exist
"""
import os
import subprocess
from pathlib import Path

import numpy as np

ASSETS_DIR = Path(__file__).parent.parent / "assets"
SOUNDS_ENABLED = os.environ.get("NEMO_SOUNDS", "true").lower() == "true"


def _generate_blip(freq: float, duration: float, fade: bool = True) -> np.ndarray:
    """generate a cute sine wave blip"""
    sr = 44100
    t = np.linspace(0, duration, int(sr * duration), False)
    wave = np.sin(2 * np.pi * freq * t) * 0.5

    if fade:
        # fade in/out for smoothness
        fade_len = int(sr * 0.02)
        wave[:fade_len] *= np.linspace(0, 1, fade_len)
        wave[-fade_len:] *= np.linspace(1, 0, fade_len)

    return (wave * 32767).astype(np.int16)


def _generate_start_sound() -> np.ndarray:
    """ascending blip - recording started"""
    sr = 44100
    blip1 = _generate_blip(440, 0.08)  # A4
    blip2 = _generate_blip(554, 0.08)  # C#5
    blip3 = _generate_blip(659, 0.12)  # E5
    gap = np.zeros(int(sr * 0.02), dtype=np.int16)
    return np.concatenate([blip1, gap, blip2, gap, blip3])


def _generate_done_sound() -> np.ndarray:
    """descending bloop - transcription done"""
    sr = 44100
    blip1 = _generate_blip(659, 0.1)   # E5
    blip2 = _generate_blip(523, 0.15)  # C5
    gap = np.zeros(int(sr * 0.03), dtype=np.int16)
    return np.concatenate([blip1, gap, blip2])


def _generate_error_sound() -> np.ndarray:
    """double low beep - error"""
    sr = 44100
    blip = _generate_blip(220, 0.1)  # A3
    gap = np.zeros(int(sr * 0.08), dtype=np.int16)
    return np.concatenate([blip, gap, blip])


def ensure_sounds():
    """create sound files if they don't exist"""
    import wave

    ASSETS_DIR.mkdir(exist_ok=True)

    sounds = {
        "blip.wav": _generate_start_sound,
        "bloop.wav": _generate_done_sound,
        "oops.wav": _generate_error_sound,
    }

    for name, generator in sounds.items():
        path = ASSETS_DIR / name
        if not path.exists():
            data = generator()
            with wave.open(str(path), 'w') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(44100)
                wf.writeframes(data.tobytes())
            print(f" created {name}")


def play(sound: str):
    """play a sound (blip, bloop, oops)"""
    if not SOUNDS_ENABLED:
        return

    ensure_sounds()

    path = ASSETS_DIR / f"{sound}.wav"
    if not path.exists():
        return

    # try different players
    for cmd in [
        ["paplay", str(path)],
        ["aplay", "-q", str(path)],
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)],
    ]:
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except FileNotFoundError:
            continue


def play_start():
    play("blip")


def play_done():
    play("bloop")


def play_error():
    play("oops")


if __name__ == "__main__":
    print("generating sounds...")
    ensure_sounds()
    print("\ntesting sounds:")
    print("blip (start)...")
    play_start()
    import time
    time.sleep(0.5)
    print("bloop (done)...")
    play_done()
    time.sleep(0.5)
    print("oops (error)...")
    play_error()
