#!/usr/bin/env python3
"""
nemo-smol client - say "nemo" to transcribe!

always listening, detects "nemo" via transcription
- say "nemo" -> starts recording
- say "nemo" again -> stops and pastes text
- or use Super+Alt+N hotkey
"""
import os
import sys
import time
import wave
import tempfile
import threading
import subprocess
from collections import deque

import numpy as np
import sounddevice as sd
import requests

# config
SERVER = os.environ.get("NEMO_SERVER", "http://127.0.0.1:8765")
HOTKEY = os.environ.get("NEMO_HOTKEY", "SUPER+ALT+N")
WAKE_WORD = os.environ.get("NEMO_WAKE_WORD", "nemo").lower()
SAMPLE_RATE = 16000
CHUNK_SECONDS = 2  # transcribe every N seconds when listening for wake word

# try evdev for hotkeys
try:
    import evdev
    HAS_EVDEV = True
except ImportError:
    HAS_EVDEV = False
    print(" evdev not installed, hotkeys disabled")

# try sounds
try:
    from . import sounds
except ImportError:
    try:
        import sounds
    except ImportError:
        class sounds:
            @staticmethod
            def play_start(): pass
            @staticmethod
            def play_done(): pass
            @staticmethod
            def play_error(): pass
            @staticmethod
            def ensure_sounds(): pass


def save_wav(audio: np.ndarray) -> str:
    """save audio to temp wav"""
    path = tempfile.mktemp(suffix=".wav")
    audio_int16 = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_int16.tobytes())
    return path


def transcribe(audio: np.ndarray) -> str:
    """send audio to server"""
    if len(audio) < SAMPLE_RATE * 0.3:
        return ""

    path = save_wav(audio)
    try:
        with open(path, 'rb') as f:
            r = requests.post(
                f"{SERVER}/transcribe",
                files={"file": ("audio.wav", f, "audio/wav")},
                timeout=30
            )
        if r.status_code == 200:
            return r.json().get("text", "").lower()
        return ""
    except:
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

    try:
        subprocess.run(["wl-copy", text], check=True, timeout=5)
        subprocess.run(
            ["ydotool", "key", "29:1", "42:1", "47:1", "47:0", "42:0", "29:0"],
            check=True, timeout=5
        )
    except Exception as e:
        print(f" paste error: {e}")


class NemoClient:
    def __init__(self):
        self.recording = False
        self.listening = True
        self.audio_buffer = deque(maxlen=SAMPLE_RATE * 60)  # 60s max
        self.record_buffer = []
        self.lock = threading.Lock()
        self.stream = None

    def start(self):
        """start always-on listening"""
        print(f"\n nemo-smol")
        print(f" server: {SERVER}")
        print(f" wake word: '{WAKE_WORD}'")
        print(f" hotkey: {HOTKEY}")
        print()

        # check server
        try:
            r = requests.get(f"{SERVER}/health", timeout=3)
            if r.status_code == 200:
                print(" server connected!")
            else:
                print(f" server error: {r.status_code}")
        except:
            print(f" server not running at {SERVER}")
            print(" start with: sudo docker compose up")
            return

        sounds.ensure_sounds()

        # start audio stream
        def audio_callback(indata, frames, time_info, status):
            audio = indata.flatten()
            with self.lock:
                if self.recording:
                    self.record_buffer.append(audio.copy())
                else:
                    self.audio_buffer.extend(audio)

        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype=np.float32,
            callback=audio_callback,
            blocksize=1024
        )
        self.stream.start()

        # start hotkey listener
        if HAS_EVDEV:
            threading.Thread(target=self._hotkey_loop, daemon=True).start()

        print(f"\n say '{WAKE_WORD}' or press {HOTKEY}!")
        print(" Ctrl+C to exit\n")

        # main loop - listen for wake word
        self._listen_loop()

    def _listen_loop(self):
        """continuously check for wake word"""
        try:
            while self.listening:
                time.sleep(CHUNK_SECONDS)

                if self.recording:
                    continue

                # get recent audio
                with self.lock:
                    if len(self.audio_buffer) < SAMPLE_RATE * 1:
                        continue
                    audio = np.array(list(self.audio_buffer))
                    self.audio_buffer.clear()

                # check for wake word
                text = transcribe(audio)
                if WAKE_WORD in text:
                    print(f" heard '{WAKE_WORD}'!")
                    self._start_recording()

        except KeyboardInterrupt:
            print("\n bye!")
            self.listening = False
            if self.stream:
                self.stream.stop()

    def _start_recording(self):
        """start recording mode"""
        with self.lock:
            if self.recording:
                return
            self.recording = True
            self.record_buffer = []
            self.audio_buffer.clear()

        sounds.play_start()
        print(" recording... say 'nemo' to stop")

        # wait for stop word
        threading.Thread(target=self._wait_for_stop, daemon=True).start()

    def _wait_for_stop(self):
        """wait for stop word while recording"""
        check_interval = 1.5  # check every 1.5s

        while self.recording:
            time.sleep(check_interval)

            with self.lock:
                if not self.recording or len(self.record_buffer) < 2:
                    continue
                # check last 2 seconds for stop word
                recent = np.concatenate(self.record_buffer[-int(SAMPLE_RATE * 2 / 1024):])

            text = transcribe(recent)
            if WAKE_WORD in text:
                print(f" heard '{WAKE_WORD}' - stopping")
                self._stop_recording()
                return

    def _stop_recording(self):
        """stop recording and transcribe"""
        with self.lock:
            if not self.recording:
                return
            self.recording = False

            if not self.record_buffer:
                sounds.play_error()
                return

            audio = np.concatenate(self.record_buffer)
            self.record_buffer = []

        # transcribe full recording
        text = transcribe(audio)

        # remove wake words from output
        for word in [WAKE_WORD, f"hey {WAKE_WORD}", f"{WAKE_WORD}."]:
            text = text.replace(word, "").strip()

        if text:
            sounds.play_done()
            paste(text)
        else:
            sounds.play_error()
            print(" no speech detected")

    def toggle(self):
        """toggle recording (for hotkey)"""
        with self.lock:
            is_recording = self.recording

        if is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _hotkey_loop(self):
        """listen for hotkey"""
        import select

        target = self._parse_hotkey(HOTKEY)
        if not target:
            return

        devices = []
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
                caps = dev.capabilities()
                if evdev.ecodes.EV_KEY in caps:
                    avail = set(caps[evdev.ecodes.EV_KEY])
                    if target.issubset(avail):
                        devices.append(dev)
                    else:
                        dev.close()
                else:
                    dev.close()
            except:
                pass

        if not devices:
            print(" no keyboards found for hotkey")
            return

        print(f" hotkey ready on {len(devices)} keyboard(s)")

        pressed = set()
        active = False

        try:
            while self.listening:
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
                                            if target.issubset(pressed) and not active:
                                                active = True
                                                self.toggle()
                                        elif ev.value == 0:
                                            pressed.discard(ev.code)
                                            if not target.issubset(pressed):
                                                active = False
                            except:
                                pass
        finally:
            for d in devices:
                try:
                    d.close()
                except:
                    pass

    def _parse_hotkey(self, s: str) -> set:
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


def main():
    client = NemoClient()
    client.start()


if __name__ == "__main__":
    main()
