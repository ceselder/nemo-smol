# nemo-smol

> *hey nemo!* - a tiny, adorable local speech-to-text friend for linux

**nemo-smol** is a minimal, cute local speech-to-text app. just say "nemo" to start talking, say "nemo" again to stop. your words appear like magic!

```
       ,---.
      /     \      "hey nemo!"
     |  o o  |
      \  ~  /       -> transcribes your speech
       `---'        -> pastes into active window
        \_/         -> all locally, no cloud!
```

## features

-  **wake word "nemo"** - just say it to start/stop recording
-  **fully local** - your voice never leaves your machine
-  **cpu-friendly** - runs great without gpu (parakeet 0.6b)
-  **cute sounds** - delightful blips and bloops
-  **wayland native** - works on gnome, kde, sway, hyprland
-  **hotkey backup** - Super+Alt+N also works

## quick start

```bash
# clone
git clone https://github.com/ceselder/nemo-smol.git
cd nemo-smol

# install deps
pip install -r requirements.txt

# add yourself to input group (for hotkeys)
sudo usermod -aG input $USER
# logout and back in!

# start server (terminal 1)
python src/server.py

# start client (terminal 2)
python src/client.py
```

## usage

**option 1: wake word (coolest)**
1. say **"hey nemo"** or just **"nemo"**
2.  *blip!* - nemo is listening
3. speak naturally
4. say **"nemo"** again to stop
5.  *bloop!* - text appears in your window!

**option 2: hotkey**
1. press **Super+Alt+N**
2. speak
3. press **Super+Alt+N** again
4.  done!

## install as service

```bash
# copy services
cp config/*.service ~/.config/systemd/user/

# enable
systemctl --user daemon-reload
systemctl --user enable --now nemo-server nemo-client

# check
systemctl --user status nemo-server nemo-client
```

## docker (server only)

```bash
docker build -t nemo-server .
docker run -p 8765:8765 nemo-server
```

## config

| env var | default | description |
|---------|---------|-------------|
| `NEMO_SERVER` | `http://127.0.0.1:8765` | server url |
| `NEMO_HOTKEY` | `SUPER+ALT+N` | keyboard shortcut |
| `NEMO_WAKE_WORD` | `nemo` | wake word |
| `NEMO_SOUNDS` | `true` | play cute sounds |

## requirements

```bash
# arch
sudo pacman -S wl-clipboard ydotool portaudio python-pip

# enable ydotool
systemctl --user enable --now ydotool

# python deps
pip install -r requirements.txt
```

## sounds

nemo comes with cute sounds:
-  `blip.wav` - listening started
-  `bloop.wav` - transcription done
-  `oops.wav` - something went wrong

## how it works

```
          you                     nemo-smol
           |                          |
   "hey nemo!"  ------------------>
           |                      wake word detected!
   "hello world" ----------------->
           |                      recording...
   "nemo"  ----------------------->
           |                      stop word detected!
           |                          |
           |    <-- transcribe -->    server
           |                          |
    "hello world"  <---------------
           |                      pasted!
```

## why "nemo"?

- it's the name of nvidia's asr framework (NeMo)
- nemo means "nobody" in latin (privacy vibes)
- it's a cute fish name
- easy to say and remember

## credits

- nvidia parakeet 0.6b for amazing local asr
- onnx-asr for cpu optimization
- you for using this smol friend!

---

*made with  and a sprinkle of * ✨

**say "hey nemo" to get started!**
