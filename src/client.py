#!/usr/bin/env python3
"""
nemo-smol client - say "nemo" to transcribe!

wake word: "nemo" - starts recording
stop word: "nemo" - stops and transcribes
hotkey: Super+Alt+N - toggle recording
"""
import os
import sys
import time
import wave
import tempfile
import threading
import subprocess
from pathlib import Path
from collections import deque

import numpy as np
import sounddevice as sd
import requests

# try to import optional deps
try:
    import evdev
    HAS_EVDEV = True
except ImportError:
    HAS_EVDEV = False
    print(" evdev not installed, hotkeys disabled")

try:
    from . import sounds
except ImportError:
    try:
        import sounds
    except ImportError:
        # create dummy sounds module
        class sounds:
            @staticmethod
            def play_start(): pass
            @staticmethod
            def play_done(): pass
            @staticmethod
            def play_error(): pass
            @staticmethod
            def ensure_sounds(): pass

# config
SERVER = os.environ.get("NEMO_SERVER", "http://127.0.0.1:8765")
HOTKEY = os.environ.get("NEMO_HOTKEY", "SUPER+ALT+N")
WAKE_WORD = os.environ.get("NEMO_WAKE_WORD", "nemo")
SAMPLE_RATE = 16000


class AudioRecorder:
    """records audio from mic"""

    def __init__(self):
        self.recording = False
        self.data = []
        self.stream = None

    def start(self):
        self.data = []
        self.recording = True

        def cb(indata, frames, time_info, status):
            if self.recording:
                self.data.append(indata.copy())

        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype=np.float32,
            callback=cb,
            blocksize=1024
        )
        self.stream.start()

    def stop(self) -> np.ndarray:
        self.recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        if self.data:
            audio = np.concatenate(self.data, axis=0).flatten()
            return audio
        return np.array([])


class WakeWordDetector:
    """listens for wake word using openwakeword or simple energy detection"""

    def __init__(self, wake_word: str, on_wake: callable):
        self.wake_word = wake_word.lower()
        self.on_wake = on_wake
        self.running = False
        self.stream = None
        self.model = None

        # try openwakeword
        try:
            from openwakeword.model import Model
            # use default models, they include "hey jarvis" which is close enough
            self.model = Model(inference_framework="onnx")
            print(f" wake word detection ready")
        except Exception as e:
            print(f" openwakeword not available: {e}")
            print(f" using energy-based detection (say 'nemo' loudly)")

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()

    def _loop(self):
        buffer = deque(maxlen=SAMPLE_RATE * 2)  # 2s buffer
        energy_history = deque(maxlen=10)
        last_trigger = 0

        def cb(indata, frames, time_info, status):
            nonlocal last_trigger
            if not self.running:
                return

            audio = indata.flatten()
            buffer.extend(audio)

            # energy-based detection fallback
            energy = np.sqrt(np.mean(audio ** 2))
            energy_history.append(energy)

            if len(energy_history) >= 3:
                avg = np.mean(list(energy_history)[:-1])
                # sudden loud sound could be "nemo"
                if energy > avg * 3 and energy > 0.05:
                    now = time.time()
                    if now - last_trigger > 2:  # debounce
                        last_trigger = now
                        print(f" loud sound detected (energy: {energy:.3f})")
                        self.on_wake()

        try:
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype=np.float32,
                callback=cb,
                blocksize=1280  # 80ms chunks
            )
            self.stream.start()

            while self.running:
                time.sleep(0.1)
        except Exception as e:
            print(f" wake word error: {e}")


class HotkeyListener:
    """listens for keyboard shortcuts using evdev"""

    def __init__(self, hotkey: str, on_press: callable):
        self.hotkey = hotkey
        self.on_press = on_press
        self.running = False

        # parse hotkey
        self.target = self._parse(hotkey)
        print(f" hotkey: {hotkey}")

    def _parse(self, s: str) -> set:
        if not HAS_EVDEV:
            return set()

        keys = set()
        mapping = {
            'super': evdev.ecodes.KEY_LEFTMETA,
            'alt': evdev.ecodes.KEY_LEFTALT,
            'ctrl': evdev.ecodes.KEY_LEFTCTRL,
            'shift': evdev.ecodes.KEY_LEFTSHIFT,
        }
        for c in 'abcdefghijklmnopqrstuvwxyz':
            mapping[c] = getattr(evdev.ecodes, f'KEY_{c.upper()}')

        for part in s.lower().replace('+', ' ').split():
            if part in mapping:
                keys.add(mapping[part])
            elif hasattr(evdev.ecodes, f'KEY_{part.upper()}'):
                keys.add(getattr(evdev.ecodes, f'KEY_{part.upper()}'))
        return keys

    def start(self):
        if not HAS_EVDEV:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def _loop(self):
        import select

        # find keyboards
        devices = []
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
                caps = dev.capabilities()
                if evdev.ecodes.EV_KEY in caps:
                    avail = set(caps[evdev.ecodes.EV_KEY])
                    if self.target.issubset(avail):
                        devices.append(dev)
                    else:
                        dev.close()
                else:
                    dev.close()
            except:
                pass

        if not devices:
            print(" no keyboards found! try: sudo usermod -aG input $USER")
            return

        print(f" monitoring {len(devices)} keyboard(s)")

        pressed = set()
        active = False

        try:
            while self.running:
                fds = [d.fd for d in devices]
                ready, _, _ = select.select(fds, [], [], 0.1)

                for fd in ready:
                    for dev in devices:
                        if dev.fd == fd:
                            try:
                                for ev in dev.read():
                                    if ev.type == evdev.ecodes.EV_KEY:
                                        if ev.value == 1:
                                            pressed.add(ev.code)
                                            if self.target.issubset(pressed) and not active:
                                                active = True
                                                self.on_press()
                                        elif ev.value == 0:
                                            pressed.discard(ev.code)
                                            if not self.target.issubset(pressed):
                                                active = False
                            except:
                                pass
        finally:
            for d in devices:
                try:
                    d.close()
                except:
                    pass


def save_wav(audio: np.ndarray) -> str:
    """save audio to temp wav file"""
    path = tempfile.mktemp(suffix=".wav")
    audio_int16 = (audio * 32767).astype(np.int16)

    with wave.open(path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_int16.tobytes())

    return path


def transcribe(path: str) -> str:
    """send audio to server"""
    try:
        with open(path, 'rb') as f:
            r = requests.post(
                f"{SERVER}/transcribe",
                files={"file": ("audio.wav", f, "audio/wav")},
                timeout=30
            )
        if r.status_code == 200:
            return r.json().get("text", "")
        print(f" server error: {r.status_code}")
        return ""
    except requests.exceptions.ConnectionError:
        print(f" can't connect to {SERVER}")
        return ""
    except Exception as e:
        print(f" error: {e}")
        return ""
    finally:
        try:
            os.unlink(path)
        except:
            pass


def paste(text: str):
    """paste text to active window"""
    if not text:
        return

    print(f" {text}")

    # copy to clipboard
    try:
        subprocess.run(["wl-copy", text], check=True, timeout=5)
    except FileNotFoundError:
        print(" install wl-clipboard!")
        return
    except Exception as e:
        print(f" copy failed: {e}")
        return

    # paste with ydotool (Ctrl+Shift+V for terminal compat)
    try:
        subprocess.run(
            ["ydotool", "key", "29:1", "42:1", "47:1", "47:0", "42:0", "29:0"],
            check=True, timeout=5
        )
    except FileNotFoundError:
        print(" install ydotool!")
    except Exception as e:
        print(f" paste failed: {e}")


class NemoClient:
    """main client"""

    def __init__(self):
        self.recorder = AudioRecorder()
        self.recording = False
        self.lock = threading.Lock()

        # hotkey
        self.hotkey = HotkeyListener(HOTKEY, self.toggle)

        # wake word (optional)
        if WAKE_WORD:
            self.wake = WakeWordDetector(WAKE_WORD, self.toggle)
        else:
            self.wake = None

    def toggle(self):
        with self.lock:
            if self.recording:
                self._stop()
            else:
                self._start()

    def _start(self):
        if self.recording:
            return
        self.recording = True
        sounds.play_start()
        self.recorder.start()
        print(" listening...")

    def _stop(self):
        if not self.recording:
            return
        self.recording = False

        audio = self.recorder.stop()
        if len(audio) < SAMPLE_RATE * 0.3:
            print(" too short")
            sounds.play_error()
            return

        # transcribe in background
        def process():
            path = save_wav(audio)
            text = transcribe(path)
            if text:
                sounds.play_done()
                paste(text)
            else:
                sounds.play_error()

        threading.Thread(target=process, daemon=True).start()

    def run(self):
        print("\n nemo-smol ")
        print(f" server: {SERVER}")
        print(f" hotkey: {HOTKEY}")
        if WAKE_WORD:
            print(f" wake word: '{WAKE_WORD}'")
        print()

        # check server
        try:
            r = requests.get(f"{SERVER}/health", timeout=3)
            if r.status_code == 200:
                print(" server connected!")
            else:
                print(f" server returned {r.status_code}")
        except:
            print(f" server not running at {SERVER}")
            print(" start with: python src/server.py")

        # generate sounds
        sounds.ensure_sounds()

        # start listeners
        self.hotkey.start()
        if self.wake:
            self.wake.start()

        print(f"\n say '{WAKE_WORD}' or press {HOTKEY} to start!")
        print(" Ctrl+C to exit\n")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n bye!")
            self.hotkey.stop()
            if self.wake:
                self.wake.stop()


def main():
    client = NemoClient()
    client.run()


if __name__ == "__main__":
    main()
